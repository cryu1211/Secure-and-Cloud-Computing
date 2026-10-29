#!/usr/bin/env python3
"""Build a PDF and its Markdown companion from actual experiment artifacts.
Uses only Python's standard library; refuses to report failed measurements.
"""
import json
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODES = ['ecmp', 'packet', 'flowlet']


class PDF:
    def __init__(self):
        self.pages = []

    def page(self, title, lines):
        operations = []
        def text(x, y, size, font, value):
            escaped = value.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            operations.append(f'BT /{font} {size} Tf {x} {y} Td ({escaped}) Tj ET')
        text(46, 748, 18, 'F1', title)
        y = 718
        for line in lines:
            # Tables start with | and preserve alignment using Courier.
            rows = [line[1:]] if line.startswith('|') else textwrap.wrap(line, 94) or ['']
            for row in rows:
                text(46, y, 9 if line.startswith('|') else 10, 'F2' if line.startswith('|') else 'F1', row)
                y -= 14
        if y < 40:
            raise ValueError(f'Page overflow: {title}')
        text(46, 26, 9, 'F1', f'Homework Two - Programmable Networks | page {len(self.pages)+1}')
        self.pages.append('\n'.join(operations).encode('ascii'))

    def save(self, path):
        objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'',
                   b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
                   b'<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>']
        kids = []
        for content in self.pages:
            page_id, stream_id = len(objects)+1, len(objects)+2
            kids.append(f'{page_id} 0 R')
            objects.append((f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
                            f'/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> '
                            f'/Contents {stream_id} 0 R >>').encode())
            objects.append(f'<< /Length {len(content)} >>\nstream\n'.encode()+content+b'\nendstream')
        objects[1] = f'<< /Type /Pages /Count {len(kids)} /Kids [{" ".join(kids)}] >>'.encode()
        data = bytearray(b'%PDF-1.4\n%HW2\n')
        offsets = [0]
        for idx, body in enumerate(objects, 1):
            offsets.append(len(data))
            data.extend(f'{idx} 0 obj\n'.encode()+body+b'\nendobj\n')
        offset = len(data)
        data.extend(f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode())
        for pos in offsets[1:]:
            data.extend(f'{pos:010} 00000 n \n'.encode())
        data.extend((f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\n'
                     f'startxref\n{offset}\n%%EOF\n').encode())
        path.write_bytes(data)


def table(s):
    lines = ['|Flow  Sent  Recv  Lost  Dup  Inversions  Late packets',
             '|----  ----  ----  ----  ---  ----------  ------------']
    for f in s['flows']:
        lines.append(f"|{f['flow']:>4}  {f['sent']:>4}  {f['received']:>4}  {f['missing']:>4}  "
                     f"{f['duplicates']:>3}  {f['inversions']:>10}  {f['late_packets']:>12}")
    return lines


def main():
    summaries = {m: json.loads((ROOT/'results'/m/'summary.json').read_text()) for m in MODES}
    for mode, summary in summaries.items():
        if not all(summary['checks'].values()):
            raise ValueError(f'Refusing to report failed {mode} experiment')
    source = (ROOT/'p4/multipath.p4').read_text().splitlines()
    def line(text):
        return next(i for i, value in enumerate(source, 1) if text in value)
    sections = []
    total = summaries['ecmp']['source_bytes']
    sections.append(('Implementation and measured results', [
        'All three milestones implemented and tested on this VM using Mininet, BMv2 simple_switch, P4_16/v1model, and Scapy. These are real data-plane measurements, not simulated estimates.',
        '',
        'One trial for each mode, with the same seed-2026 random five tuples and workload: 16 UDP flows, 2,080 packets, and '+f'{total:,} Ethernet bytes sent per mode.',
        '12 small flows: 20 x 128-byte frames; 2 medium flows: 120 x 512-byte frames; 2 large flows: 800 x 1,400-byte frames. The two large flows dominate the byte total.',
        '',
        '|Mode         Source bytes  Upper bytes  Lower bytes   Upper %',
        '|------------ ------------ ------------ ------------ --------',
        *[f"|{m:<12} {s['source_bytes']:>12,} {s['upper_bytes']:>12,} {s['lower_bytes']:>12,} {100*s['upper_fraction']:>7.2f}%" for m, s in summaries.items()],
        '',
        '|Mode         Received   Inversions   Late packets  Path changes',
        *[f"|{m:<12} {s['received_packets']:>8} {s['total_inversions']:>12} {s['total_late_packets']:>14} {s['flowlet_path_changes']:>13}" for m, s in summaries.items()],
        '',
        'Every mode passed: source bytes = S1 upper + lower bytes; each branch agrees with its intermediate-switch counter; S4 egress agrees with source; all packets arrive exactly once.',
        'ECMP has no observed reordering, but is badly imbalanced for this workload. Per-packet random choice improves byte balance and causes reordering. Flowlets avoid observed reordering while permitting path changes; their byte balance still depends on burst sizes and random choices.',
        '',
        'Results and raw evidence: results/<mode>/summary.json, sent.json, received.json, switch command logs, and flowlet-register.log.',
    ]))
    sections.append(('Milestone 1: topology, ECMP, monitoring', [
        'Task 1: topology.json defines two servers h1/h2 and four switches. scripts/run.py builds this topology with explicit port numbers and TCLink delays.',
        '',
        '|                      s2',
        '|                 2 /      \\ 2',
        '|h1 --- 1 s1                    s4 3 --- h2',
        '|                 3 \\      / 2',
        '|                      s3',
        'Upper path: S1:2 -> S2:1, S2:2 -> S4:1 (1ms per link). Lower path: S1:3 -> S3:1, S3:2 -> S4:2 (15ms per link). Host links have 0ms configured delay. Nominal forward propagation is 2ms versus 30ms, before processing and queueing.',
        '',
        f'Task 2: p4/multipath.p4 implements ECMP in balance() at line {line("action balance(")}. A CRC32 over source/destination IP, IP protocol, and UDP source/destination ports selects one of ports 2 and 3. The same five tuple always chooses the same port.',
        f'first_hop at line {line("table first_hop")} is populated only on S1, only for host-facing ingress port 1. The shared program therefore needs no extra first-hop header. S2-S4 use destination LPM forwarding. IPv4 TTL is decremented and the checksum is recomputed. Unknown destinations and unsupported traffic are dropped.',
        '',
        f'Task 3: port_bytes is a 64-bit register array (line {line("register<bit<64>")}). Egress counting at line {line("control MyEgress")} adds standard_metadata.packet_length to the outgoing port counter. Queries, ARP, and dropped packets are excluded.',
        f'answer_query() at line {line("action answer_query")} handles EtherType 0x88b5. Request: op=0, port, switch ID, nonce, 64-bit bytes. The addressed switch reads its counter, sets op=1, swaps Ethernet addresses, and sends back toward h1. Queries carry a target ID to avoid ambiguous local replies.',
        'The measurement runner queries every switch/port from h1 only after sender completion and a two-second drain. All counters begin at zero because each experiment starts fresh switches. Command files are generated in commands/; CLI reads only diagnose flowlet path changes, not traffic bytes.',
        '',
        'Run: ./run_milestone1.sh. This compiles, creates the topology, configures ECMP, sends the workload, collects in-band counters, validates delivery, and saves measured results.',
    ]))
    ecmp = summaries['ecmp']; packet = summaries['packet']; flowlet = summaries['flowlet']
    sections.append(('Milestone 2: byte balance and reordering', [
        'Task 1: scripts/workload.py generates seeded random five tuples with different frame sizes and packet counts. scripts/traffic.py sends using Scapy. Each UDP payload begins with HW2!, a 32-bit flow ID, and a 32-bit sequence number starting at zero per flow.',
        f"ECMP: {total:,} source bytes; {ecmp['upper_bytes']:,} upper bytes; {ecmp['lower_bytes']:,} lower bytes ({100*ecmp['upper_fraction']:.2f}% upper). Both large flows hash onto the lower path. Flow counts are therefore a poor proxy for byte balance.",
        'Task 2: mode=1 in balance() draws an independent random bit for each packet, selecting port 2 or 3. This offers each packet a chance to change path; byte equality is not guaranteed for a finite workload.',
        f"Per-packet: {total:,} source bytes; {packet['upper_bytes']:,} upper bytes; {packet['lower_bytes']:,} lower bytes ({100*packet['upper_fraction']:.2f}% upper).",
        'Task 3: the receiver records arrival order. scripts/analyze.py counts inversions: pairs i<j with sequence[i]>sequence[j], separately per flow. A merge-based algorithm computes the exact result in O(n log n). Late packets are also reported: arrivals with a sequence below the largest already seen. An inversion is a pair, not a unique packet.',
        f"Observed per-packet totals: {packet['total_inversions']:,} inversions and {packet['total_late_packets']:,} late packets. ECMP has zero for both. No loss or duplicates confound these results.",
        '',
        'Per-packet results for every flow:',
        *table(packet),
        '',
        'Run: ./run_milestone2.sh. The two modes use the same workload. See results/ecmp/summary.json and results/packet/summary.json for five tuples, all port counters, validation checks, and per-flow counts.',
    ]))
    sections.append(('Milestone 3: flowlet switching', [
        'Task 1: mode=2 records a valid bit, full CRC32 fingerprint, last ingress timestamp, and selected path in 65,536 register slots. A hash indexes the slot. The first packet chooses randomly; subsequent packets reuse its path until the idle gap exceeds 100,000 microseconds. Then a new random choice is permitted.',
        'BMv2 timestamps are in microseconds. The 100ms threshold exceeds the nominal 28ms path delay difference. The source sends eight bursts per flow and sleeps 250ms between global bursts. Inside a burst, flow packets are interleaved while preserving source order.',
        'Register read/modify/write blocks use @atomic. Fingerprints detect most slot collisions and initialize a new occupant rather than reusing an unrelated path. This finite hash-indexed table is not an exact flow dictionary; collision evictions can disrupt path affinity. Such behavior is a stated limitation, not a general guarantee of ordering.',
        f"Task 2: {total:,} source bytes; {flowlet['upper_bytes']:,} upper bytes; {flowlet['lower_bytes']:,} lower bytes ({100*flowlet['upper_fraction']:.2f}% upper). The diagnostic path-change register recorded {flowlet['flowlet_path_changes']} changes for existing matching flows.",
        f"Flowlet switching produced {flowlet['total_inversions']:,} inversions versus {packet['total_inversions']:,} for per-packet switching in these trials. Zero observed reordering is consistent with the threshold and pauses chosen here; large queue delays or collisions could invalidate that outcome.",
        '',
        'Flowlet results for every flow:',
        *table(flowlet),
        '',
        'Run: ./run_milestone3.sh. All mode configuration is generated into commands/s*-flowlet.txt. The shared P4 program keeps S2-S4 on destination forwarding.',
    ]))
    sections.append(('ECMP per-flow evidence and port counters', [
        'ECMP per-flow delivery and reordering:', *table(ecmp), '',
        'Outgoing data-frame bytes obtained through query packets:',
        '|Mode        Switch        Port 1        Port 2        Port 3',
        *[f"|{m:<11} {sw:<6} {counts['1']:>13,} {counts['2']:>13,} {counts['3']:>13,}"
          for m, s in summaries.items() for sw, counts in s['counters'].items()],
        '',
        'Byte units include Ethernet/IP/UDP headers and application payload. They exclude Ethernet FCS, preamble, inter-frame gap, and query traffic. The frame is unchanged in length through the fabric, so source and switch totals are directly comparable.',
    ]))
    sections.append(('Reproduction, validation, and limitations', [
        'Build and unit checks: make all. Requires p4c-bm2-ss plus Python 3; the workload and analysis tests use only the standard library.',
        'Full measurement: sudo -E /path/to/venv/bin/python3 scripts/run.py --mode all. Requires Mininet, Scapy, simple_switch, simple_switch_CLI, tc, ethtool, and privileges to create namespaces and veth links. Use the P4 lab VM with its Python environment activated.',
        'Generate updated report and ZIP: make report; make package. report.py reads saved summaries and refuses to describe experiments with failed checks. package.py includes source, build JSON, topology, commands, raw results, report PDF, and documentation; excludes hidden credentials and caches.',
        'Measurements start fresh switches per mode and explicitly wait for receiver readiness. After sending, a two-second queue drain precedes queries. The runner fails if source/path bytes disagree, intermediate-switch counters disagree, delivery has missing packets, or duplicates appear. Only its own switch and capture processes are stopped in cleanup.',
        'Unit validation checks the inversion algorithm against an independent quadratic oracle on random sequences and checks workload uniqueness, counts, mixed sizes, and repeatability. p4c compiles the program without warnings. End-to-end integration uses the actual P4 JSON on four BMv2 switches.',
        'Limitations: one measured trial per mode; no statistical confidence claim. The source seed reproduces tuples and sizes, but BMv2 random choices and host scheduling can vary. Software-switch queueing and CPU contention can alter balance, delay, and reordering. Flowlet ordering depends on the actual worst-case delay difference, not just nominal link delay.',
        'The educational pipeline supports Ethernet, fixed-header IPv4, and unfragmented UDP. It does not implement ARP, IPv4 options, fragmentation, TCP, arbitrary host applications, or a production forwarding/control plane. Workload source IPs are spoofed to create random five tuples; the receiver records raw packets with Scapy.',
        'Query packets are intended for this isolated lab and have no authentication. The counters are 64-bit and do not saturate. Queries are collected after traffic drains rather than attempting an atomic multi-switch snapshot.',
        '',
        'Primary documentation used to verify target behavior:',
        'https://github.com/p4lang/behavioral-model/blob/main/docs/simple_switch.md',
        'https://github.com/p4lang/p4c/blob/main/p4include/v1model.p4',
        '',
        'Source files were authored for this assignment; tutorial implementations were not copied. No externally hosted service is needed to run or package this work.',
    ]))
    pdf = PDF()
    for title, lines in sections:
        pdf.page(title, lines)
    pdf.save(ROOT/'report.pdf')
    markdown = '\n\n'.join('# '+title+'\n\n'+'\n\n'.join(lines) for title, lines in sections)
    (ROOT/'report.md').write_text(markdown+'\n')
    print(f'Generated report.pdf ({len(pdf.pages)} pages) and report.md from measured results')


if __name__ == '__main__':
    main()
