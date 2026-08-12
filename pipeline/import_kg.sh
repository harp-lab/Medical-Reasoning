#!/usr/bin/env bash
set -euo pipefail

MR=/home.na1/ad.wsu.edu/aayush.shrestha/pvt/projects/MedicalReasoning
SLOG=/home.na1/ad.wsu.edu/aayush.shrestha/pvt/projects/slog
RACKET=/home.na1/ad.wsu.edu/aayush.shrestha/pvt/racket/bin
SRC="$MR/data/import_ready"

DBNAME="${1:-}"
[ -n "$DBNAME" ] || { echo "usage: $0 <new-db-name>" >&2; exit 1; }
case "$DBNAME" in */*) echo "bad db name: $DBNAME" >&2; exit 1 ;; esac

REAL="$MR/data/db/$DBNAME"
[ -e "$REAL" ] && { echo "$REAL already exists; delete it first" >&2; exit 1; }

export PATH="$RACKET:$PATH"
command -v racket >/dev/null || { echo "racket not on PATH" >&2; exit 1; }

for f in kg2_edges.15.tsv kg2_nodes.13.tsv kg2_node_synonym.2.tsv kg2_node_publication.2.tsv; do
  [ -f "$SRC/$f" ] || { echo "missing $SRC/$f" >&2; exit 1; }
done

echo "[$(date +%T)] importing $SRC as '$DBNAME' (~40 min)"
cd "$SLOG"
racket compiler/csv2db.rkt -d $'\t' "$SRC" "$DBNAME"

mv "$SLOG/data/$DBNAME" "$REAL"
ln -sfn "$REAL" "$SLOG/data/$DBNAME"

echo "[$(date +%T)] done -> $REAL"
ls "$SLOG/data/$DBNAME/"
