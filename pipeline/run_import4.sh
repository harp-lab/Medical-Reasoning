#!/usr/bin/env bash
# Fourth attempt.  Everything happens on /tmp (local NVMe, no home quota):
#   - previous run died because quoting filled the 100G home quota and
#     truncated kg2_edges.15.tsv at 53.7M of 57.0M rows
#   - the source edges file is CRLF, so a stray \r was ending up inside the
#     last column of every row
#
# One pass from the original 18-column file: keep columns 1,3-6,9-18 (drops
# the two provenance blobs and the unique per-row id), strip \r, quote every
# cell.  No intermediate files.
set -euo pipefail

M=/home.na1/ad.wsu.edu/aayush.shrestha/pvt/Projects/MedicalReasoning
SLOG=/home.na1/ad.wsu.edu/aayush.shrestha/pvt/Projects/slog
W=/tmp/$USER/kgwork
IN="$W/in"
export PATH="$HOME/racket/bin:$PATH"

mkdir -p "$IN" "$W/run/data"

# chomp then drop a trailing \r; escape backslash before quote so unescaping
# reverses cleanly; split with limit -1 keeps trailing empty columns
QUOTE='chomp; s/\r$//; my @F = split /\t/, $_, -1;
       for (@F){ s/\\/\\\\/g; s/"/\\"/g; $_ = "\"$_\"" }
       print join("\t",@F),"\n"'

echo "[$(date +%T)] edges: cut + strip CR + quote, straight from the original (~20 min)..."
LC_ALL=C cut -f1,3-6,9-18 "$M/data/interim/kg2_import/kg2_edges.18.tsv" \
  | perl -ne "$QUOTE" > "$IN/kg2_edges.15.tsv"
echo "[$(date +%T)]   edges done"

for f in kg2_nodes.13.tsv kg2_node_synonym.2.tsv kg2_node_publication.2.tsv; do
  echo "[$(date +%T)] quoting $f..."
  perl -ne "$QUOTE" "$M/data/interim/kg2_ready/$f" > "$IN/$f"
done

echo "[$(date +%T)] verifying..."
for f in kg2_edges.15.tsv kg2_nodes.13.tsv kg2_node_synonym.2.tsv kg2_node_publication.2.tsv; do
  LC_ALL=C awk -F'\t' -v F="$f" '
    {n++; c[NF]++; if(index($0,"\r")) cr++}
    END{printf "  %-28s lines=%-11d CR=%-3d fields:", F, n, cr+0
        for(k in c) printf " %s->%d", k, c[k]; print ""}' "$IN/$f"
done
df -h /tmp | tail -1

echo "[$(date +%T)] starting import as dataTest3..."
cd "$W/run"
LOG="$W/import.log"
echo "started: $(date)" > "$LOG"
setsid nohup racket "$SLOG/compiler/csv2db.rkt" -d $'\t' "$IN" dataTest3 >> "$LOG" 2>&1 < /dev/null &
sleep 20
echo "[$(date +%T)] racket pids now: $(ps -u $USER -o pid=,comm= | awk '$2=="racket"{printf "%s ", $1}')"
echo "[$(date +%T)] db will land at $W/run/data/dataTest3 -- log: $LOG"
