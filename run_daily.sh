#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs
{
  echo "=== Run started: $(date -Iseconds) ==="
  source .venv/bin/activate
  python run_daily.py
  echo "=== Run finished: $(date -Iseconds) ==="
  echo
} >> logs/run.log 2>&1
