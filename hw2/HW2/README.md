# Homework Two: Programmable Networks

A complete P4_16/v1model implementation of ECMP, per-packet random routing,
flowlet switching, and in-band per-port byte monitoring on four BMv2 switches.
Includes all three milestones, including the graduate flowlet milestone.

## Run on the P4 lab VM

Activate the VM's Python environment containing Mininet and Scapy. For this VM:

```bash
source /home/p4/src/p4dev-python-venv/bin/activate
make all
./run_milestone1.sh     # topology + ECMP + byte queries
./run_milestone2.sh     # ECMP versus per-packet; per-flow reordering
./run_milestone3.sh     # flowlet switching and reordering
```

Or run all modes in one invocation:

```bash
make build
sudo -E "$(command -v python3)" scripts/run.py --mode all
make report
make package
```

Root access is needed for Mininet, namespace creation, link configuration, and
raw packet sockets. `make all`, reporting, and packaging do not require root.
Dependencies: Python 3, Mininet, Scapy, p4c-bm2-ss, simple_switch,
simple_switch_CLI, iproute2/tc, and ethtool. There are no tutorial Python module
dependencies. The PDF generator uses only Python's standard library.

Each mode creates fresh switches/counters. The runner owns and cleans up its
processes and links. Avoid simultaneous runs or another lab using s1-s4 or
Thrift ports 9090-9093. An experiment replaces its saved results; regenerate
the report and package afterward.

## Files by milestone

| File | Purpose |
| --- | --- |
| `topology.json` | Two hosts, diamond of four switches, explicit ports, link delays |
| `p4/multipath.p4` | All three routing modes, TTL/checksum, counters, query replies |
| `scripts/run.py` | Mininet setup, BMv2 lifecycle, control plane, measurements |
| `scripts/workload.py` | Seeded random five tuples and mixed flow/frame sizes |
| `scripts/traffic.py` | Scapy sender, capture receiver, in-band queries |
| `scripts/analyze.py` | Per-flow inversion/late/loss counts, byte validation |
| `commands/s*-<mode>.txt` | Generated CLI configuration used in each measured run |
| `results/<mode>/` | Raw sent/received packet records, summary, and diagnostics |
| `scripts/report.py` | PDF and Markdown generated from measured summaries |
| `scripts/package.py` | ZIP submission, excluding hidden files and caches |
| `tests/test_analysis.py` | Independent inversion oracle and workload checks |

S1 connects h1 on port 1, S2 on port 2, and S3 on port 3. S2/S3 connect S1 on
port 1 and S4 on port 2. S4 connects S2 on port 1, S3 on port 2, and h2 on port
3. The upper branch adds 2ms nominal propagation; the lower adds 30ms.

The first-hop table is populated only on S1's port 1. All other switches use
destination-based forwarding with the same compiled program. Mode 0 is ECMP,
mode 1 is per-packet random choice, and mode 2 is flowlet random choice on an
idle gap greater than `flowlet_gap_us` (100ms by default). Source bursts are
separated by 250ms. Registers have 65,536 slots, a valid bit, and CRC32 tags;
collisions can still evict flows. Ordering is not guaranteed under arbitrary
queue delays or hash collisions.

## Measurements

Read `report.pdf` for measured byte totals, per-flow reordering, milestone
mapping, commands, interpretation, and limitations. `report.md` is a searchable
companion. Actual values also appear in `results/<mode>/summary.json`.

Each run sends 16 UDP flows, 2,080 frames, and 2,393,600 Ethernet bytes.
Small/medium/large frame sizes are 128/512/1,400 bytes. Five tuples and source
sequence order are seeded; BMv2 random choices and scheduling are not.
Byte totals exclude FCS, preamble, inter-frame gaps, and query traffic.

An inversion counts an out-of-order *pair* within a flow. Late packets count
arrivals below the highest sequence already seen. Missing/duplicate packets
are reported separately and cause experiment validation to fail.

### In-band counter queries

The runner launches queries inside h1, after a two-second drain. A request
uses EtherType `0x88b5` and a 12-byte header: `op:u8, port:u8, switch_id:u8,
nonce:u8, bytes:u64` in network byte order. Request op=0; reply op=1. The target
reads its egress data-byte counter and returns toward h1. Query frames never
increment data counters. To query manually *inside the h1 namespace while the
topology is running*:

```bash
python3 scripts/traffic.py query --iface h1-eth1 --switch 1 --port 2
python3 scripts/traffic.py query --iface h1-eth1 --switch 1 --port 3
python3 scripts/traffic.py query --iface h1-eth1 --switch 4 --port 3
```

These commands are called automatically by the runner. Do not query from a
switch's own root interface: BMv2 may see local packet injection there.

The pipeline handles fixed-header IPv4 and unfragmented UDP. The Scapy workload
uses spoofed source addresses and direct Ethernet destination addressing;
ARP and general-purpose host IP connectivity are outside this assignment's
measurement setup. Primary target references:
[BMv2 metadata](https://github.com/p4lang/behavioral-model/blob/main/docs/simple_switch.md)
and [v1model declarations](https://github.com/p4lang/p4c/blob/main/p4include/v1model.p4).
