#!/usr/bin/env python3
"""Report exact per-flow inversions in O(n log n), loss, and byte balance."""
import json
from collections import Counter
from pathlib import Path


def inversions(values):
    def merge(a):
        if len(a) < 2:
            return a, 0
        left, x = merge(a[:len(a)//2])
        right, y = merge(a[len(a)//2:])
        i = j = 0
        out = []
        count = x + y
        while i < len(left) and j < len(right):
            if left[i] <= right[j]:
                out.append(left[i]); i += 1
            else:
                out.append(right[j]); j += 1
                count += len(left) - i
        return out + left[i:] + right[j:], count
    return merge(list(values))[1]


def analyze(directory, counters, mode, changes):
    directory = Path(directory)
    source = json.loads((directory / 'sent.json').read_text())
    arrivals = json.loads((directory / 'received.json').read_text())
    rows = []
    expected_keys = {(s['flow'], s['sequence']) for s in source['sent']}
    observed_keys = [(r['flow'], r['sequence']) for r in arrivals]
    if set(observed_keys) - expected_keys:
        raise RuntimeError('Receiver captured unexpected packets')
    for f in source['flows']:
        seq = [a['sequence'] for a in arrivals if a['flow'] == f['id']]
        # Late packets are those below the largest sequence seen so far.
        largest = -1
        late = 0
        for n in seq:
            late += n < largest
            largest = max(largest, n)
        rows.append(dict(flow=f['id'], five_tuple=[f['src'], f['dst'], 17, f['sport'], f['dport']],
                         sent=f['packets'], received=len(seq),
                         missing=f['packets']-len(set(seq)),
                         duplicates=len(seq)-len(set(seq)),
                         inversions=inversions(seq), late_packets=late))
    upper, lower = counters['s1']['2'], counters['s1']['3']
    total = sum(s['bytes'] for s in source['sent'])
    checks = dict(source_equals_paths=total == upper+lower,
                  upper_path_consistent=upper == counters['s2']['2'],
                  lower_path_consistent=lower == counters['s3']['2'],
                  receiver_egress_consistent=total == counters['s4']['3'],
                  no_loss=all(r['missing'] == 0 for r in rows),
                  no_duplicates=all(r['duplicates'] == 0 for r in rows))
    summary = dict(mode=mode, seed=source['seed'], source_bytes=total,
                   upper_bytes=upper, lower_bytes=lower,
                   upper_fraction=upper/(upper+lower) if upper+lower else 0,
                   received_bytes=sum(r['bytes'] for r in arrivals),
                   sent_packets=len(source['sent']), received_packets=len(arrivals),
                   total_inversions=sum(r['inversions'] for r in rows),
                   total_late_packets=sum(r['late_packets'] for r in rows),
                   flowlet_path_changes=changes, counters=counters, checks=checks, flows=rows)
    (directory / 'summary.json').write_text(json.dumps(summary, indent=2))
    if not all(checks.values()):
        raise RuntimeError(f'Validation failed: {checks}')
    return summary
