#!/usr/bin/env bash
# Launch the long-lived Slog session server.
#
# Toolchain: slog passes clang-only flags (-ferror-limit, -fbracket-depth) to the
# plugin compiler, so clang must be first on PATH and must be the same clang the
# daemon was built with (they share one OpenMP runtime).  gmp/boost headers come
# from the same env.
#
# Memory: the cap is normally enforced by launching slogd under
# `systemd-run --user`, which fails on an ssh session with no user D-Bus.
# SLOG_NO_MEM_CAP=1 skips that launcher; SLOG_MEM_MAX is still honoured, since
# the driver derives SLOG_MEM_BYTES (~90%) from it and the daemon enforces that
# itself by sampling its own RSS.  So an overrun stops cleanly instead of
# thrashing into swap.  Loading the KG needs ~81 GB, hence the headroom.
set -euo pipefail

TC=/home.na1/ad.wsu.edu/aayush.shrestha/pvt/miniconda3/envs/slogtc
MR=/home.na1/ad.wsu.edu/aayush.shrestha/pvt/projects/MedicalReasoning
RACKET=/home.na1/ad.wsu.edu/aayush.shrestha/pvt/racket/bin

export PATH="$TC/bin:$RACKET:$PATH"
export CPATH="$TC/include"
export LIBRARY_PATH="$TC/lib"
export LD_LIBRARY_PATH="$TC/lib:${LD_LIBRARY_PATH:-}"
export SLOG_NO_MEM_CAP=1
export SLOG_MEM_MAX="${SLOG_MEM_MAX:-150G}"
export SLOG_SERVER_PORT="${SLOG_SERVER_PORT:-8642}"
export KG2_SLOG_DB="${KG2_SLOG_DB:-dataTest4}"

# Refuse rather than start a load that will thrash.  No reservation is possible
# here (cgroups are root-only, memlock is 8 MB, no systemd user session), so a
# pre-flight check is the only guard before the daemon's own RSS cap.
NEED_GB="${KG2_MIN_FREE_GB:-100}"
AVAIL_GB=$(awk '/^MemAvailable:/ {print int($2/1048576)}' /proc/meminfo)
if [ "$AVAIL_GB" -lt "$NEED_GB" ]; then
  echo "refusing to start: ${AVAIL_GB}G available, want ${NEED_GB}G" >&2
  echo "  (override with KG2_MIN_FREE_GB=<gb>)" >&2
  exit 1
fi
echo "[kg2-server] ${AVAIL_GB}G available, starting" >&2

exec racket "$MR/slog/slog_server.rkt"
