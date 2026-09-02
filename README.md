# MedicalReasoning

Querying the RTX-KG2 biomedical knowledge graph with Datalog (Slog), exposed to Claude
Code through a local MCP server.

## Prerequisites

**A clone of [harp-lab/slog](https://github.com/harp-lab/slog)** must exist on the same
machine. By convention it sits beside this repo:

```
projects/
  MedicalReasoning/     this repo
  slog/                 the slog clone
```

That path is currently **hardcoded** and must be edited if your layout differs:

- `slog/slog_server.rkt` — the `require` of `compiler/session.rkt`, plus `SLOG-ROOT` and
  `MR-ROOT`
- `slog/kg2-server.sh` — `TC`, `MR`, `RACKET`
- `.mcp.json` — the Python interpreter and `KG2_DATA_DIR`

**Toolchain.** Racket, and the clang that the slog daemon was built with — they share an
OpenMP runtime, and slog passes clang-only flags. `kg2-server.sh` puts the right one on
`PATH`.

**Python.** `pip install -r requirements.txt`.

**Data.** Not in the repo. Source is the public RTX-KG2 2.8.1 export.

## Running

```bash
slog/kg2-server.sh      # loads the KG, then opens port 8642
```

The load takes several minutes and leaves `slogd` holding ~170–200 GB. It happens
**before** the port opens, so no query ever pays for it. The launcher refuses to start
with less than 100 GB free.

Stop it with `slog/kg2-stop.sh`.

The MCP server starts and stops with Claude Code, per `.mcp.json`. Restarting it is free;
it does not reload the graph.

## The database

`data/db/rtx_kg2_281` — 56,965,146 edges and 11,342,763 nodes, plus synonyms, publications,
and the `kg2_norm` mapping, all in one database. 9.8 GB on disk. Never modified.

slog resolves database names as `data/<name>` relative to its own root, so the database has
to be reachable at `slog/data/rtx_kg2_281`. Either put it there directly, or keep it here and
symlink.

`slog/setup.slog` runs at session load and derives four views over the raw relations.

## Relations you query

```
edge(subj, pred, obj)                        asserted, non-negated edges
edge_dir(subj, pred, obj, aspect, direction) plus the qualifier columns
edge_rel(subj, ptype, obj)                   source-specific predicate
node(id, name, category)
kg2_norm(kg2_id, preferred_id)               canonical CURIE, for cross-vocab joins
```

KG2 does not merge equivalent entities, so joining two independently derived sets on the
raw id returns zero rows. Join on the canonical key from `kg2_norm`. Column maps for the
raw 15- and 13-column relations are in `docs/NOTES.md`.

## Layout

```
mcp/
  mcp_server.py       the 5 MCP tools (FastMCP)
  kg2_core.py         entity grounding, predicate list, result naming
  slog_client.py      TCP client for the resident session
  mr_logging.py       per-session log + summary CSV + query archive
  mr_stats.py         per-run timing, from the daemon's own statistics
  instructions/       kg2.md -- query conventions, sent to the model
slog/
  slog_server.rkt     the resident session; holds the KG
  kg2-server.sh       launcher (toolchain env, memory pre-flight, SLOG_OPT=0,
                      SLOG_MULTIPLAN=1)
  kg2-stop.sh         stops the server and its slogd
  setup.slog          views over the raw relations
  query.slog          the program run_slog executes; overwritten per query
preprocess/           NodeNorm mapping -> the kg2_norm table
logs/                 one folder per MCP session
docs/NOTES.md         measurements, the cost model, and open questions
```

## Query cost

Roughly `9s compile + 13s per derived relation`.

Compilation is pinned to `-O0` via `SLOG_OPT=0` in `kg2-server.sh`

Join-plan selection is on via `SLOG_MULTIPLAN=1` (also `kg2-server.sh`): eligible
rules carry an alternative tail order that the daemon meters interpreted, on real
data, before the stratum runs, and the cheaper one runs. `SLOG_MULTIPLAN_INDEX`
is `budget:1`, capping each relation at one new FULL ordering — `eager` unions
every arm's needs onto the giant EDB rules, and `free` was measured to attach no
arms at all (feature on, selecting nothing). Turn the whole thing off with an
empty value:
`SLOG_MULTIPLAN= slog/kg2-server.sh`. The flag is part of slog's job hash, so
changing it recompiles every stratum once.

## Logs

One folder per MCP session:

```
logs/<YYYYMMDD-HHMMSS>/
    mcp.log                     step-by-step narrative
    summary.csv                 one row per tool call
    queries/NNN_run_slog.slog   the exact program each run executed
```
