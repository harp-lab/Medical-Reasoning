# MedicalReasoning

Querying the RTX-KG2 biomedical knowledge graph with Datalog, exposed to Claude Code
through a local MCP server.

## Layout

```
mcp/          the MCP server
  mcp_server.py       tool definitions (FastMCP)
  kg2_core.py         query execution + NCATS entity grounding
  instructions/       kg2.md -- query conventions, surfaced to the client
slog/         Slog engine integration
  slog_hold.rkt       resident session: loads the KG once and holds it
  kg2-hold.sh         launcher (sets the clang/gmp/boost toolchain env)
pipeline/     data preparation
  run_import4.sh      builds the Slog database from the source TSVs
  count_predicates.py
notebooks/    exploratory work
docs/         STATUS.md -- current state, data layout, how Slog works
archive/      superseded scripts, .dl scratch files, old Souffle output
data/
  db/         Slog binary databases.  dataTest3 is the live one.
  source/     original 2.8.1 exports and column headers
  interim/    intermediate TSVs from the import pipeline
  reference/  predicate lists, node index
```

## The database

`data/db/dataTest3` is the imported KG: 56,965,146 edges, 11,342,763 nodes, plus synonym
and publication tables. Slog requires databases at `data/<name>` relative to *its own*
repo, so `slog/data/dataTest3` is a symlink pointing here. Moving `data/db/dataTest3`
means retargeting that symlink.

Column mappings for both tables are in `docs/STATUS.md` §3. Read them before writing
queries — the edge relation has 15 positional columns.

## Running

The MCP server is configured in `.mcp.json` and starts with Claude Code.

Slog queries need the toolchain env that `slog/kg2-hold.sh` sets: clang from the
`slogtc` conda env, plus `SLOG_NO_MEM_CAP=1` (no user D-Bus for `systemd-run`) and
`SLOG_MEM_MAX`. Loading the KG takes about 5 minutes and ~81 GB of RAM.

Rebuilding the database from scratch: `pipeline/run_import4.sh`, roughly 40 minutes. It
writes intermediates to `/tmp` to stay off the 100 GB home quota.
