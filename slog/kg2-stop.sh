#!/usr/bin/env bash
# Stop the Slog session server AND its daemon.
#
# slogd is a child of the Racket server but is not killed with it: killing only
# the parent leaves an orphaned slogd holding the whole database (~140 GB) with
# nothing driving it.  Always stop through here.
set -uo pipefail

pkill -f slog_server.rkt 2>/dev/null && echo "stopped slog_server.rkt"
sleep 2
if pgrep -u "$USER" slogd > /dev/null 2>&1; then
  pkill -u "$USER" slogd 2>/dev/null
  sleep 3
  # SIGTERM is often ignored mid-ingest; escalate rather than leak the memory
  if pgrep -u "$USER" slogd > /dev/null 2>&1; then
    echo "slogd ignored SIGTERM; sending SIGKILL"
    pkill -9 -u "$USER" slogd 2>/dev/null
    sleep 3
  fi
fi

if pgrep -u "$USER" slogd > /dev/null 2>&1; then
  echo "WARNING: slogd still running:" >&2
  ps -u "$USER" -o pid=,rss=,comm= | grep slogd >&2
  exit 1
fi

echo "stopped; $(awk '/^MemAvailable:/ {print int($2/1048576)}' /proc/meminfo)G available"
