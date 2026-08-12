# MedicalReasoning

Querying the RTX-KG2 biomedical knowledge graph with Datalog (Slog), exposed to Claude
Code through a local MCP server.

## Layout

```
mcp/          the MCP server
  mcp_server.py       5 tool definitions (FastMCP)
  kg2_core.py         NCATS grounding, predicate list, result naming
  instructions/       kg2.md -- query conventions, surfaced to the client
  slog_client.py      TCP client for the resident Slog session
slog/
  slog_server.rkt     resident session: loads the KG once and holds it
  kg2-server.sh       launcher (clang/gmp/boost toolchain env + memory cap)
  kg2-stop.sh         stops the server AND its orphan-prone slogd
  setup.slog          views over the raw relations, run at session load
preprocess/
  build_kg2_norm.py   NodeNorm mapping for all 11.3M nodes -> quoted TSV
  build_norm_db.sh    that TSV -> the kg2norm database
pipeline/
  import_kg.sh        data/import_ready -> a new KG database
eval/
  run_questions.py    run a question list through claude -p, record everything
data/
  db/                 the Slog databases (dataTest3, kg2norm)
  import_ready/       quoted, import-ready TSVs -- the durable rebuild set
  norm_ready/         kg2_norm.2.tsv only (csv2db imports whole folders)
  source/             original 2.8.1 node export and column headers
  reference/          predicate lists
```

## The databases

Both live in `data/db/` and are symlinked into the slog repo's `data/`, because Slog
resolves database names as `data/<name>` relative to its own repo.

| db | contents |
|---|---|
| `dataTest3` | 56,965,146 edges, 11,342,763 nodes, synonyms, publications |
| `kg2norm` | `kg2_norm(kg2_id, preferred_id)`, 11,342,763 rows |

`slog_server.rkt` opens `dataTest3` and links `kg2norm` into the same session, so both
are queryable together. `dataTest3` is never modified.

## Relations you query

```
edge(subj, pred, obj)                        asserted, non-negated edges
edge_dir(subj, pred, obj, aspect, direction) plus qualifier columns
edge_rel(subj, ptype, obj)                   source-specific predicate
node(id, name, category)
kg2_norm(kg2_id, preferred_id)               canonical CURIE, for cross-vocab joins
```

KG2 does not merge equivalent entities, so joining two derived sets on the raw id
returns zero rows. Join on the canonical key from `kg2_norm`. Column mappings for the
raw 15- and 13-column relations are at the top of `slog/setup.slog`.

## Running

1. Start the session server: `slog/kg2-server.sh`. First query loads the KG — about six
   minutes and ~97 GB. Stop it with `slog/kg2-stop.sh`, never a bare `kill`.
2. The MCP server starts with Claude Code, per `.mcp.json`.

## Rebuilding

```bash
python preprocess/build_kg2_norm.py    # ~2 h, resumable
./preprocess/build_norm_db.sh          # ~3 min
./pipeline/import_kg.sh dataTest4      # ~40 min, from data/import_ready
```

The raw unquoted 18-column edge export lives on `/tmp/$USER/kg2_raw` — it is 40 GB and
only needed to regenerate `data/import_ready`, which is already quoted. Everything under
`/tmp` is expendable; re-download RTX-KG2 2.8.1 if it is wiped.
