#!/usr/bin/env bash
# Quick diagnostic: where does edge-loading time actually go?
# Avoids reading the full 38GB file — uses a small sample + a small
# random-offset probe on the real file instead. Should finish in <30s.
set -euo pipefail

EDGES="${EDGES:-rtx-kg2_edges_2.8.1.tsv}"
BINARY="${BINARY:-./test_instrumented}"
NFS_SERVER="${NFS_SERVER:-svm1.vcea.wsu.edu}"
NFS_MOUNT="${NFS_MOUNT:-/home.na1}"
SAMPLE_ROWS="${SAMPLE_ROWS:-500000}"   # small enough to load in ~seconds
DD_MB="${DD_MB:-300}"                   # size of the raw-I/O probe chunk

[[ -f "$EDGES" ]]   || { echo "Cannot find $EDGES"; exit 1; }
[[ -x "$BINARY" ]]  || { echo "Cannot find/execute $BINARY"; exit 1; }

SAMPLE_DIR=$(mktemp -d)
trap 'rm -rf "$SAMPLE_DIR"' EXIT

echo "############################################"
echo "# 1. Network latency: node -> storage server"
echo "############################################"
ping -c 5 -q "$NFS_SERVER" | tail -3

echo
echo "############################################"
echo "# 2. Cumulative NFS RPC stats (server-side response time)"
echo "############################################"
nfsiostat "$NFS_MOUNT" || echo "(nfsiostat unavailable)"

echo
echo "############################################"
echo "# 3. Raw disk->RAM read speed (fresh random 300MB chunk, avoids cache)"
echo "############################################"
FILE_BYTES=$(stat -c%s "$EDGES")
FILE_MB=$(( FILE_BYTES / 1048576 ))
OFFSET_MB=$(( RANDOM % (FILE_MB - DD_MB - 1) ))
echo "reading ${DD_MB}MB starting at offset ${OFFSET_MB}MB of a ${FILE_MB}MB file..."
t0=$(date +%s.%N)
dd if="$EDGES" of=/dev/null bs=1M skip="$OFFSET_MB" count="$DD_MB" status=none
t1=$(date +%s.%N)
DD_SECONDS=$(awk "BEGIN{print $t1-$t0}")
DD_MBPS=$(awk "BEGIN{printf \"%.1f\", $DD_MB/$DD_SECONDS}")
echo "-> ${DD_MB}MB in ${DD_SECONDS}s = ${DD_MBPS} MB/s (raw I/O, no parsing)"

echo
echo "############################################"
echo "# 4. Parse + index speed on a small sample (real Souffle code, warm cache)"
echo "############################################"
SAMPLE_FILE="$SAMPLE_DIR/$(basename "$EDGES")"   # must match filename baked into the binary
# Sample from a random middle offset, not the head of the file -- rows are
# grouped (e.g. by source/predicate), so the first N lines have a different
# avg line length than the file as a whole and skew any extrapolation.
# Pull a local chunk via dd first, then trim lines in separate (non-piped)
# steps -- piping tail into head under `set -o pipefail` makes an early
# head exit look like a failure (SIGPIPE on the upstream tail).
RAW_CHUNK="$SAMPLE_DIR/raw_chunk.tsv"
CHUNK_MB=$(( SAMPLE_ROWS*2/1000 + 50 ))   # generous margin, assumes <=2KB/line
SAMPLE_OFFSET_MB=$(( FILE_MB/4 + (RANDOM % (FILE_MB/2)) ))
echo "sampling ~${SAMPLE_ROWS} rows from a ${CHUNK_MB}MB chunk at offset ${SAMPLE_OFFSET_MB}MB..."
dd if="$EDGES" of="$RAW_CHUNK" bs=1M skip="$SAMPLE_OFFSET_MB" count="$CHUNK_MB" status=none
# drop first AND last line -- dd cuts the chunk off mid-line at both ends.
# `head -n -1` must read to EOF to know where the end is, so no early-exit
# SIGPIPE against the upstream `tail` here.
tail -n +2 "$RAW_CHUNK" | head -n -1 > "$SAMPLE_DIR/trimmed.tsv"
head -n "$SAMPLE_ROWS" "$SAMPLE_DIR/trimmed.tsv" > "$SAMPLE_FILE"
mkdir -p "$SAMPLE_DIR/out"
"$BINARY" -F "$SAMPLE_DIR" -D "$SAMPLE_DIR/out" 2> "$SAMPLE_DIR/timing.log" >/dev/null
cat "$SAMPLE_DIR/timing.log"

LINE=$(grep '^\[readAll\]' "$SAMPLE_DIR/timing.log")
TUPLES=$(echo "$LINE" | grep -oP 'tuples=\K[0-9]+')
PARSE_S=$(echo "$LINE" | grep -oP 'parse\(read\+decode\)=\K[0-9.eE+-]+')
INSERT_S=$(echo "$LINE" | grep -oP 'insert\(index\)=\K[0-9.eE+-]+')
SAMPLE_BYTES=$(stat -c%s "$SAMPLE_FILE")

echo
echo "############################################"
echo "# 5. Extrapolated estimate for the full file"
echo "############################################"
SCALE=$(awk "BEGIN{print $FILE_BYTES/$SAMPLE_BYTES}")
EST_ROWS=$(awk "BEGIN{printf \"%.0f\", $TUPLES*$SCALE}")
EST_PARSE_CPU=$(awk "BEGIN{printf \"%.1f\", $PARSE_S*$SCALE}")
EST_INSERT=$(awk "BEGIN{printf \"%.1f\", $INSERT_S*$SCALE}")
EST_IO=$(awk "BEGIN{printf \"%.1f\", $FILE_MB/$DD_MBPS}")

printf "%-45s %10s\n" "estimated full-file row count" "$EST_ROWS"
printf "%-45s %10ss\n" "raw disk/NFS I/O (from dd probe)" "$EST_IO"
printf "%-45s %10ss\n" "parse+decode CPU cost (from sample, warm)" "$EST_PARSE_CPU"
printf "%-45s %10ss\n" "B-tree index build (from sample, warm)" "$EST_INSERT"
TOTAL=$(awk "BEGIN{printf \"%.1f\", $EST_IO+$EST_PARSE_CPU+$EST_INSERT}")
printf "%-45s %10ss\n" "sum (rough total estimate)" "$TOTAL"
echo
awk -v io="$EST_IO" -v parse="$EST_PARSE_CPU" -v ins="$EST_INSERT" 'BEGIN{
  total=io+parse+ins
  printf "I/O share:     %5.1f%%\n", 100*io/total
  printf "parse share:   %5.1f%%\n", 100*parse/total
  printf "index share:   %5.1f%%\n", 100*ins/total
}'
