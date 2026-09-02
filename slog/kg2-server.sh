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
RACKET=/home.na1/ad.wsu.edu/aayush.shrestha/pvt/racket/bin

# Derived, not spelled absolutely -- the tree moved once (both checkouts now sit
# under MR/) and every hardcoded path broke together.  slog_server.rkt locates
# the slog checkout the same way, as MedicalReasoning's sibling.
MR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export PATH="$TC/bin:$RACKET:$PATH"
export CPATH="$TC/include"
export LIBRARY_PATH="$TC/lib"
export LD_LIBRARY_PATH="$TC/lib:${LD_LIBRARY_PATH:-}"
export SLOG_NO_MEM_CAP=1
export SLOG_MEM_MAX="${SLOG_MEM_MAX:-150G}"
export SLOG_SERVER_PORT="${SLOG_SERVER_PORT:-8642}"
export KG2_SLOG_DB="${KG2_SLOG_DB:-rtx_kg2_281}"

# -O0 only.  slog's default ("tiered") runs the eager -O0 build and then spawns a
# detached -O2 build that hot-swaps in; measured here, -O2 makes no difference
# (12.6s vs 12.4s fixpoint on the same query) because runtime is dominated by
# fixed per-stratum overhead rather than generated-code quality.  The background
# builds only cost disk.
export SLOG_OPT=interp #"${SLOG_OPT:-0}"

# Multi-plan join selection (slog docs/join-planning-assessment.md).  Off by
# default in slog, so without this the planner emits only its static argmax
# order and the daemon's interp-measured arm selection has nothing to choose
# between.  With it on, eligible dynamic rules get one alternative tail order as
# an interpreted sibling, the daemon meters both on real data before the stratum
# runs, and the cheaper arm wins.  Unset here means "on"; pass an EMPTY value
# (SLOG_MULTIPLAN= ./kg2-server.sh) to turn it back off, which is why this uses
# ${VAR-default} and not ${VAR:-default}.
#
# The flag changes plan bytes, so it joins slog's job hash: the first start after
# this lands recompiles every stratum cold.
#
# index=budget:1 caps each relation at ONE new FULL ordering.  This is not the
# `eager` default because an extra FULL ordering is 32 btrees of complete
# permuted tuple copies, and eager's union lands that on the giant EDB rules
# first (slog's notes record a silent 4G OOM on a far smaller relation than
# kg2_edges).  It is not `free` either: measured on tests/multiplan/flip_mini,
# `free` attached ZERO arms (0 arm-trace lines vs 89 under both eager and
# budget:1), i.e. `free` leaves the flag on while selecting nothing.  budget:1
# was the cheapest policy that actually attaches arms.
#
# Residual risk: one extra ordering on kg2_edges is still large in absolute
# terms.  SLOG_MEM_MAX above is the backstop -- an overrun stops cleanly.  If it
# does overrun, `free` is the retreat (feature effectively off) rather than a fix.
export SLOG_MULTIPLAN="${SLOG_MULTIPLAN-1}"
export SLOG_MULTIPLAN_INDEX="${SLOG_MULTIPLAN_INDEX:-budget:1}"

# Set SLOG_ARM_DEBUG=1 for the attach/pick/UNPIN trace on stderr -- the way to
# confirm arms are actually being metered and picked.

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
