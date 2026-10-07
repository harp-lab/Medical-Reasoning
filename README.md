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

## `orion` — the same session, from a terminal

The MCP `run_slog` tool is a thin client over a plain TCP/JSON-lines protocol, so a model
is not required to reach the engine. `orion` is that client with a CLI on it:

```bash
./orion status                       # up, still loading, or orphaned
./orion execute slog/query.slog      # write the .slog yourself, run it yourself
./orion execute slog/query.slog -v   # + the run timeline and how each number was derived
./orion execute slog/query.slog -vv  # + the $stat_* tables, join plans and the program
./orion dump '$stat_fixpoint'        # any relation in the live session
./orion columns                      # where each summary.csv column comes from
```

### Where the time goes

`-v` is a profiler. Its centre is the **run timeline**: every line the session emitted,
with the wall clock between lines.

```
+    1,033 ms  (+    1,033 ms)  (pipeline (pos 12) (evaluation "eval-1a0639…")
                                          (strata (s 0 10 …) … +5 more (s …))
                                          (rel kg2_edges (v 0 3 56965146))
                                          (rel result (v 0 12 1627)))
+   82,965 ms  (+   81,925 ms)  (arms (g 0 1 0 "query.slog:12") … +23 more (g …))
+   82,965 ms  (+        0 ms)  (fixpoint 4 "6ba66f12" 2 6506.819)
+  157,179 ms  (+   74,214 ms)  (paused … (timing (call-ms 8051) (total-ms 8051))
                                          (cause (budget time)))
```

The gaps are the finding. On this KG the two fixpoints above account for 22s of a 165s
run; the rest sits in stretches where nothing is emitted at all, bounded by `(arms …)` and
`(paused …)`. `reloadInsertBatches` — the whole-DB re-stage armed after every fixpoint —
emits nothing and is not timed, and `SLOG_MULTIPLAN` arm metering runs before each stratum.
`-v` ends with a ledger of every gap ≥ 1s and, beside each, the timing that line carries
about itself, which for `(arms …)` is nothing.

Long lines are shortened by **structure**, not by character count: a run of repeated
siblings keeps the first few and says how many more there were, so `(pipeline …)` still
shows its per-relation tuple counts instead of being cut at 160 characters. Nothing is
computed or inferred — every character printed came from the line. `--max-lines` caps how
many rows one line may occupy (default 6, `0` lifts it).

Every run also writes `NNN_run_slog.stream`: each echoed line whole, uncapped, written as
it arrives — so `tail -f` works during a run, and an interrupted run still leaves what it
got. The stamp is separated by a tab; everything after it is the line as echoed. This needs
the tee in `slog/slog_server.rkt`, so a server started before that change reports `no-tee`
and the timeline falls back to the socket reply, where long lines are stubbed at 160.

The stream is teed at slog's `#:echo`, not at slogd's stdout, so it is not quite the
daemon's own bytes: `compiler/session.rkt` synthesizes some lines that look like daemon
lines (`(tier …)`, `(activated …)`, `(recount …)`) and turns `(error …)` into an exception
rather than echoing it.

### Reading summary.csv

`-v` then shows **what we derived**, every number tagged with its source and the arithmetic
that produced it — `daemon`, `session`, `build`, `client`, `program`, `model`, `os`, defined
in `mcp/mr_provenance.py`.

That tagging is the other reason the tool exists. A `summary.csv` row prints `fixpoint_ms`
— the daemon's own accounting — in the same flat CSV as `predicted_s`, which is
`9.0 + 13.0 × n_derived_rels` with both constants hardcoded in `mr_stats.py` and nothing
about the run feeding them. They look equally measured and are not. (The measured per-stratum
overhead in `logs/` is nearer 60–70s than the 13s that constant assumes.) `orion columns`
prints the mapping for every column without needing the server.

### Practicalities

Runs land in `logs/orion/<ts>/` in the same format as the MCP sessions, and their summary
rows carry a `via-orion` note. Both clients share one session and serialize on its
semaphore, so a run started here blocks one started from Claude. Unlike the MCP tool there
is no permission prompt: typing the command is the confirmation, and a run is still minutes
and tens of GB.

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

## Net-effect mode

Off by default. A normal query locks its direction (`(= prod -1)`) and returns whatever
matched. With the flag on -- `run_slog(net=True, goal=-1)`, or
`./orion execute --net [--goal 1]` -- the query instead writes every route it matches,
in **both** directions, into `evidence(drug, effect, route, strength)`, and
`slog/net.slog` is appended to decide, in Slog, whether each candidate drug's net
evidence favours the goal:

- `net_dir` -- a flat lattice: a drug whose routes all agree settles on that direction,
  one with routes both ways settles on `(top)`.
- `net_best` -- a max lattice per side: the strongest route for and against, where a
  route is as strong as its weakest hop (2 curated, 1 literature).
- `net_paths` -- a set lattice per side: distinct routes, counted with `csize`.

Unopposed drugs are good; contested ones are decided by the stronger best route, then
by route count. `result` becomes one row per candidate: `drug, verdict, basis,
routes_for, routes_against, best_for, best_against`. The query never states a
direction; `goal` is substituted into the layer as a literal. `mcp/mr_net.py` does the
assembly and checks, and drops every layer relation before a run, because a session
segment adds to a relation an earlier one wrote. The query contract and an example are
in `mcp/instructions/kg2.md`, "Net-effect mode".

## Layout

```
mcp/
  mcp_server.py       the 5 MCP tools (FastMCP)
  kg2_core.py         entity grounding, predicate list, result naming
  mr_net.py           net-effect mode: appends slog/net.slog, ranks the verdicts
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
  net.slog            the net-effect layer, appended to query.slog in net mode
preprocess/           NodeNorm mapping -> the kg2_norm table
tests/net_toy/        toy-graph regression for slog/net.slog (run.sh; no KG needed)
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

One folder per MCP session, and one per `orion` invocation under `logs/orion/`:

```
logs/<YYYYMMDD-HHMMSS>/
    mcp.log                     step-by-step narrative
    summary.csv                 one row per tool call
    queries/NNN_run_slog.slog   the exact program each run executed
    NNN_run_slog.stream         every line the session echoed, whole (orion runs)
```

`orion columns` explains where every `summary.csv` column's value actually comes from —
worth reading once before quoting a number out of that file, since the daemon's own
measurements and a hardcoded cost model sit side by side in it.
