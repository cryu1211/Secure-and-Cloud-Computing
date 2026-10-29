#!/usr/bin/env python3
"""Own BMv2 processes, Mininet topology, control plane, and measurements."""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from mininet.net import Mininet
from mininet.node import Switch
from mininet.link import TCLink
from mininet.log import setLogLevel
from analyze import analyze

ROOT = Path(__file__).resolve().parents[1]


class Bmv2(Switch):
    def __init__(self, name, thrift_port, **kwargs):
        super().__init__(name, **kwargs)
        self.thrift_port = thrift_port
        self.process = None
        self.logfile = None

    def start(self, controllers):
        args = ['simple_switch', '--thrift-port', str(self.thrift_port), '--device-id', self.name[1:]]
        for port, intf in self.intfs.items():
            if port:
                args += ['-i', f'{port}@{intf.name}']
        args += [str(ROOT / 'build/multipath.json')]
        self.logfile = open(ROOT / 'results' / f'{self.name}.log', 'w')
        self.process = subprocess.Popen(args, stdout=self.logfile, stderr=subprocess.STDOUT)

    def stop(self, deleteIntfs=True):
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait()
        if self.logfile:
            self.logfile.close()
        super().stop(deleteIntfs)


def cli(sw, commands):
    result = subprocess.run(['simple_switch_CLI', '--thrift-port', str(sw.thrift_port)],
                            input=commands, text=True, capture_output=True, timeout=10)
    if result.returncode or re.search(r'Error|Invalid', result.stdout + result.stderr):
        raise RuntimeError(f'{sw.name} CLI failed: {result.stdout}\n{result.stderr}')
    return result.stdout


def wait_process(process, timeout, name):
    code = process.wait(timeout=timeout)
    if code:
        raise RuntimeError(f'{name} exited with {code}; see its log')


def experiment(mode, seed):
    config = json.loads((ROOT / 'topology.json').read_text())
    output = ROOT / 'results' / mode
    output.mkdir(parents=True, exist_ok=True)
    for flag in ['ready', 'stop']:
        (output / flag).unlink(missing_ok=True)
    net = Mininet(controller=None, build=False, link=TCLink)
    switches = {name: net.addSwitch(name, cls=Bmv2, thrift_port=9090+i)
                for i, name in enumerate(['s1', 's2', 's3', 's4'])}
    hosts = {name: net.addHost(name, ip=info['ip']+'/24', mac=info['mac'])
             for name, info in config['hosts'].items()}
    nodes = {**switches, **hosts}
    for link in config['links']:
        net.addLink(nodes[link['a']], nodes[link['b']], port1=link['a_port'],
                    port2=link['b_port'], delay=link['delay'], max_queue_size=10000)
    receiver = None
    sender = None
    logs = []
    try:
        net.build(); net.start()
        # Disable NIC aggregation: sequence counts must represent individual frames.
        for node in nodes.values():
            for intf in node.intfList():
                if intf.name != 'lo':
                    node.cmd(f'ethtool -K {intf.name} rx off tx off tso off gso off gro off 2>/dev/null')
        for name, sw in switches.items():
            deadline = time.monotonic() + 10
            while True:
                try:
                    cli(sw, 'show_tables\n')
                    break
                except (RuntimeError, subprocess.TimeoutExpired):
                    if sw.process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError(f'{name} failed to start; see results/{name}.log')
                    time.sleep(0.1)
        routes = {'s1': (2, 1), 's2': (2, 1), 's3': (2, 1), 's4': (3, 1)}
        for name, sw in switches.items():
            dest_port, src_port = routes[name]
            commands = (f'table_add MyIngress.destination MyIngress.forward 10.0.2.2/32 => {dest_port}\n'
                        f'table_add MyIngress.destination MyIngress.forward 10.0.1.1/32 => {src_port}\n')
            for target in range(1, 5):
                if target == int(name[1:]):
                    commands += f'table_add MyIngress.query_route MyIngress.answer_query {target} =>\n'
                elif name == 's1':
                    next_port = 3 if target == 3 else 2
                    commands += f'table_add MyIngress.query_route MyIngress.forward {target} => {next_port}\n'
                elif name == 's2' and target == 4:
                    commands += 'table_add MyIngress.query_route MyIngress.forward 4 => 2\n'
            if name == 's1':
                number = {'ecmp': 0, 'packet': 1, 'flowlet': 2}[mode]
                commands += f'table_add MyIngress.first_hop MyIngress.balance 1 => {number} {config["flowlet_gap_us"]}\n'
            (ROOT / 'commands' / f'{name}-{mode}.txt').write_text(commands)
            (output / f'{name}-cli.log').write_text(cli(sw, commands))
        h1, h2 = hosts['h1'], hosts['h2']
        receive_log = open(output / 'receive.log', 'w'); logs.append(receive_log)
        receiver = h2.popen([sys.executable, str(ROOT/'scripts/traffic.py'), 'receive',
                             '--iface', 'h2-eth1', '--output', str(output/'received.json'),
                             '--ready', str(output/'ready'), '--stop', str(output/'stop')],
                            stdout=receive_log, stderr=subprocess.STDOUT)
        deadline = time.monotonic()+10
        while not (output/'ready').exists():
            if receiver.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Receiver did not become ready; see receive.log')
            time.sleep(0.05)
        send_log = open(output/'send.log', 'w'); logs.append(send_log)
        sender = h1.popen([sys.executable, str(ROOT/'scripts/traffic.py'), 'send', '--iface', 'h1-eth1',
                           '--output', str(output/'sent.json'), '--seed', str(seed)],
                          stdout=send_log, stderr=subprocess.STDOUT)
        wait_process(sender, 120, 'sender')
        # Queue drain, well beyond 30ms maximum propagation delay.
        time.sleep(2)
        (output/'stop').touch()
        wait_process(receiver, 10, 'receiver')
        counters = {}
        # Every query originates at h1 and carries the intended switch ID.
        for name in switches:
            counters[name] = {}
            for port in [1, 2, 3]:
                response = h1.cmd(f'{sys.executable} {ROOT}/scripts/traffic.py query --iface h1-eth1 --port {port} --switch {name[1:]}')
                try:
                    value = int(response.strip())
                except ValueError:
                    raise RuntimeError(f'Counter query failed: {response}')
                counters[name][str(port)] = value
        diagnostics = cli(switches['s1'], 'register_read MyIngress.flowlet_changes 0\n')
        (output/'flowlet-register.log').write_text(diagnostics)
        match = re.search(r'\[0\]\s*=\s*(\d+)', diagnostics)
        changes = int(match.group(1)) if match else None
        summary = analyze(output, counters, mode, changes)
        print(json.dumps({k: summary[k] for k in ['mode', 'source_bytes', 'upper_bytes',
              'lower_bytes', 'total_inversions', 'flowlet_path_changes', 'checks']}, indent=2))
    finally:
        for process in [sender, receiver]:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
        net.stop()
        for log in logs:
            log.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['ecmp', 'packet', 'flowlet', 'all'], default='all')
    parser.add_argument('--seed', type=int, default=2026)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Mininet requires root; run sudo -E python3 scripts/run.py')
    setLogLevel('warning')
    for mode in ['ecmp', 'packet', 'flowlet'] if args.mode == 'all' else [args.mode]:
        experiment(mode, args.seed)


if __name__ == '__main__':
    main()
