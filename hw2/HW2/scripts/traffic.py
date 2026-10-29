#!/usr/bin/env python3
"""Scapy traffic generator, destination collector, and in-band counter client."""
import argparse
import json
import random
import struct
import time
from pathlib import Path
from scapy.all import Ether, IP, UDP, Raw, AsyncSniffer, conf

MAGIC = b'HW2!'


from workload import plan


def generate(iface, output, seed, pause):
    flows = plan(seed)
    rng = random.Random(seed + 1)
    sock = conf.L2socket(iface=iface)
    sent = []
    started = time.monotonic()
    # Eight bursts per flow; preserves sequence order within each five tuple.
    for burst in range(8):
        pending = []
        for f in flows:
            lo, hi = f['packets'] * burst // 8, f['packets'] * (burst + 1) // 8
            pending.extend((f, seq) for seq in range(lo, hi))
        # Randomly interleave flows without permuting a flow's sequence numbers.
        queues = {f['id']: [] for f in flows}
        for f, seq in pending:
            queues[f['id']].append(seq)
        while any(queues.values()):
            active = [f for f in flows if queues[f['id']]]
            rng.shuffle(active)
            for f in active:
                seq = queues[f['id']].pop(0)
                body = struct.pack('!4sII', MAGIC, f['id'], seq)
                pkt = (Ether(src='00:00:00:00:01:01', dst='00:00:00:00:02:02') /
                       IP(src=f['src'], dst=f['dst'], id=seq % 65536) /
                       UDP(sport=f['sport'], dport=f['dport'], chksum=0) /
                       Raw(body + bytes(f['frame_bytes'] - 42 - len(body))))
                wire = bytes(pkt)
                sock.send(wire)
                sent.append(dict(flow=f['id'], sequence=seq, bytes=len(wire),
                                 seconds=time.monotonic() - started))
                time.sleep(0.00005)
        if burst < 7:
            time.sleep(pause)
    sock.close()
    Path(output).write_text(json.dumps(dict(seed=seed, flows=flows, sent=sent), indent=2))


def receive(iface, output, ready, stop):
    arrivals = []
    def collect(pkt):
        if UDP in pkt:
            payload = bytes(pkt[UDP].payload)
            if len(payload) >= 12 and payload[:4] == MAGIC:
                _, fid, seq = struct.unpack('!4sII', payload[:12])
                arrivals.append(dict(flow=fid, sequence=seq, bytes=len(pkt),
                                     timestamp=float(pkt.time)))
    sniffer = AsyncSniffer(iface=iface, prn=collect, store=False)
    sniffer.start()
    # AsyncSniffer's started_callback runs after the capture socket is ready.
    # Use the event provided by Scapy rather than a fixed startup sleep.
    while not hasattr(sniffer, 'stop_cb'):
        if not sniffer.running:
            raise RuntimeError('capture failed to start')
        time.sleep(0.01)
    Path(ready).touch()
    while not Path(stop).exists():
        time.sleep(0.05)
    sniffer.stop()
    Path(output).write_text(json.dumps(arrivals, indent=2))


def query(iface, port, switch_id=1, nonce=1):
    replies = []
    def collect(pkt):
        if Ether in pkt and pkt[Ether].type == 0x88b5:
            raw = bytes(pkt[Ether].payload)
            if len(raw) >= 12:
                op, found_port, found_switch, found_nonce, value = struct.unpack('!BBBBQ', raw[:12])
                if (op, found_port, found_switch, found_nonce) == (1, port, switch_id, nonce):
                    replies.append(value)
    sniffer = AsyncSniffer(iface=iface, prn=collect, store=False)
    sniffer.start()
    while not hasattr(sniffer, 'stop_cb'):
        if not sniffer.running:
            raise RuntimeError('query capture failed')
        time.sleep(0.01)
    sock = conf.L2socket(iface=iface)
    req = bytes(Ether(src='02:00:00:00:00:01', dst='02:00:00:00:00:02', type=0x88b5) /
                Raw(struct.pack('!BBBBQ', 0, port, switch_id, nonce, 0) + bytes(34)))
    try:
        for _ in range(3):
            sock.send(req)
            deadline = time.monotonic() + 1
            while not replies and time.monotonic() < deadline:
                time.sleep(0.01)
            if replies:
                return replies[0]
        raise RuntimeError(f'No query reply on {iface}, port {port}')
    finally:
        sniffer.stop()
        sock.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['send', 'receive', 'query'])
    p.add_argument('--iface', required=True)
    p.add_argument('--output')
    p.add_argument('--ready')
    p.add_argument('--stop')
    p.add_argument('--port', type=int, default=1)
    p.add_argument('--switch', type=int, default=1)
    p.add_argument('--seed', type=int, default=2026)
    p.add_argument('--pause', type=float, default=0.25)
    a = p.parse_args()
    if a.action == 'send':
        generate(a.iface, a.output, a.seed, a.pause)
    elif a.action == 'receive':
        receive(a.iface, a.output, a.ready, a.stop)
    else:
        print(query(a.iface, a.port, a.switch))


if __name__ == '__main__':
    main()
