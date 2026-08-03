#!/usr/bin/env bash
# Launch the resident slog session (slog/slog_hold.rkt) with the toolchain env.
#
# SLOG_NO_MEM_CAP=1 skips the systemd-run launcher (no user D-Bus on an ssh
# session), but SLOG_MEM_MAX is still honoured: the driver derives a soft RSS
# cap of 90% from it and the daemon enforces that itself, sampling its own RSS
# during ingestion.  So an overrun stops cleanly instead of eating into swap.
set -euo pipefail

TC=/home.na1/ad.wsu.edu/aayush.shrestha/pvt/miniconda3/envs/slogtc
export PATH="$TC/bin:$HOME/racket/bin:$PATH"
export CPATH="$TC/include"
export LIBRARY_PATH="$TC/lib"
export LD_LIBRARY_PATH="$TC/lib:${LD_LIBRARY_PATH:-}"
export SLOG_NO_MEM_CAP=1
export SLOG_MEM_MAX="${SLOG_MEM_MAX:-150G}"     # -> ~135G soft cap in-daemon

exec racket /home.na1/ad.wsu.edu/aayush.shrestha/pvt/Projects/MedicalReasoning/slog/slog_hold.rkt
