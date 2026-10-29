"""Deterministic mixed-size random five-tuple workload (no network access)."""
import random


def plan(seed=2026):
    rng = random.Random(seed)
    flows = []
    seen = set()
    for fid in range(16):
        while True:
            five = (f'10.1.{rng.randrange(1, 255)}.{rng.randrange(1, 255)}',
                    '10.0.2.2', 17, rng.randrange(1024, 65536), rng.randrange(1024, 65536))
            if five not in seen:
                seen.add(five)
                break
        count, size = (20, 128) if fid < 12 else ((120, 512) if fid < 14 else (800, 1400))
        flows.append(dict(id=fid, src=five[0], dst=five[1], protocol=five[2],
                          sport=five[3], dport=five[4], packets=count, frame_bytes=size))
    return flows

