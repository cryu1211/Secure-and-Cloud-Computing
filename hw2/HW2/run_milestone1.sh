#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
make build
sudo -E "$(command -v python3)" scripts/run.py --mode ecmp
