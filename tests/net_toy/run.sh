#!/usr/bin/env bash
# Regression test for the net-effect layer, on a 30-edge toy graph -- no KG, no
# session server, nothing shared.  Rerun after any edit to slog/net.slog or
# mcp/mr_net.py.
#
#   tests/net_toy/run.sh
#
# For goal -1 and goal 1: assemble query.slog + slog/net.slog with mr_net (exactly
# as run_slog(net=True) does), prepend graph.slog, run it standalone under
# SLOG_OPT=interp (the server's setting), and diff `result` against the expected
# TSV.  A cold run compiles slog's driver first and takes a few minutes.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MR="$(cd "$HERE/../.." && pwd)"
SLOG="$(cd "$MR/.." && pwd)/slog"
TC=/home.na1/ad.wsu.edu/aayush.shrestha/pvt/miniconda3/envs/slogtc
RACKET=/home.na1/ad.wsu.edu/aayush.shrestha/pvt/racket/bin

export PATH="$TC/bin:$RACKET:$PATH"
export CPATH="$TC/include"
export LIBRARY_PATH="$TC/lib"
export LD_LIBRARY_PATH="$TC/lib:${LD_LIBRARY_PATH:-}"
export SLOG_NO_MEM_CAP=1
export SLOG_MEM_MAX=8G
export SLOG_OPT=interp

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fail=0
for goal in -1 1; do
  prog="$WORK/net_goal$goal.slog"
  python3 - "$MR" "$HERE" "$goal" > "$prog" <<'EOF'
import sys
from pathlib import Path
mr, here, goal = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
sys.path.insert(0, str(mr / "mcp"))
import mr_net
print((here / "graph.slog").read_text())
print(mr_net.assemble((here / "query.slog").read_text(), goal))
EOF
  (cd "$SLOG" && timeout 900 racket compiler/run.rkt --no-banner \
       --debug-dir "$WORK/out$goal" "$prog" > "$WORK/run$goal.log" 2>&1) || {
    echo "FAIL goal $goal: run error"; tail -20 "$WORK/run$goal.log"; fail=1; continue; }
  # debug-dir rows are space-separated with quoted strings; normalise to TSV
  python3 - "$WORK/out$goal/result.csv" > "$WORK/got$goal.tsv" <<'EOF'
import re, sys
rows = ["\t".join(c.strip('"') for c in re.findall(r'"[^"]*"|-?\d+', line))
        for line in open(sys.argv[1]) if line.strip()]
print("\n".join(sorted(rows)))
EOF
  if diff "$HERE/expected_goal$goal.tsv" "$WORK/got$goal.tsv"; then
    echo "PASS goal $goal ($(wc -l < "$WORK/got$goal.tsv") candidates)"
  else
    echo "FAIL goal $goal: result differs (expected < > got)"; fail=1
  fi
done
exit $fail
