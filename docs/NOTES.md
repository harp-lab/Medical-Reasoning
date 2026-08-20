# Implementation notes

Things that are not obvious from reading the code, and measurements that would be
expensive to re-derive. Human-facing: `mcp/instructions/kg2.md` is the model-facing
document and nothing here belongs in it.

Measured August 2026 on this deployment (503 GB machine, `slogd -t 47`, database on NFS).

## Architecture

Four processes, two independent lifetimes.

```
Claude Code
  └── mcp/mcp_server.py        spawned by Claude Code (see .mcp.json), stdio JSON-RPC
        └── slog/slog_server.rkt   started by hand, TCP 127.0.0.1:8642
              └── slog/daemon/slogd    holds the knowledge graph in RAM
```

The bottom pair is started with `slog/kg2-server.sh` and lives until killed. The top is
started and killed by Claude Code. **Restarting the MCP server is free; it does not reload
the knowledge graph.** Only restarting `slog_server.rkt` costs the load.

`slog_server.rkt` is a thin adapter: it accepts one JSON object per request, dispatches
three verbs (`run`, `dump`, `drop`) to slog's `session-*` API, and replies with one JSON
object. A semaphore serialises requests, because there is a single session.

The Racket server requires `session.rkt` from a clone of
[harp-lab/slog](https://github.com/harp-lab/slog) by absolute path. That clone is a
prerequisite, not part of this repo. Pinned commit: `e8d1108`.

## Cost model

```
query wall time  ~=  ~9s compile   (only when the program text changes)
                  +  ~13s per derived relation
```

A derived relation is any relation that appears as a rule head — every `table` beyond the
base views. The engine must complete and store each one before anything reads it, and each
of those boundaries costs ~13s of fixed overhead.

**Data volume is free.** A rule over `biolink:affects` (4.7M edges, 166k results) and one
over `biolink:directly_physically_interacts_with` (12k edges, 4.9k results) both cost ~13s.
Row counts, predicate selectivity and result size do not affect runtime.

**Stage count is everything.** 1/2/3/4 derived relations measured 13/27/40/65s. Inlining
six anchor CURIEs as literals instead of collecting them into a membership relation took an
identical query (same 1,569 answers) from 36.4s to 25.1s.

Compilation is `-O0`, and it blocks. `SLOG_OPT` defaults to `tiered`: clang builds `-O0`
eagerly and the query runs on that, while a detached `-O2` build lands in the background
and hot-swaps in. `SLOG_OPT=2` blocks for `-O2`; `SLOG_OPT=0` disables the background
builds. Optimization level makes no measurable difference here — the same query measured
12.6s on `-O0` and 12.4s / 11.9s on the cached `-O2`.

Re-running byte-identical program text skips compilation entirely; build artifacts are
named by content hash.

Incremental reuse does work and is visible: the same question asked twice went from 7,864
rule firings and 22.2s of fixpoint to 0 firings and 13.5s. It recovers the work but cannot
go below the per-stage floor.

## The open question: what is the ~13s per stage

Unresolved. Worth putting to the slog authors — the measurements below are precise enough
to make the question concrete.

It is **not**: compilation (measured separately), I/O (near-zero disk reads),
interpretation (the code is compiled native), optimization level, rows examined, rows
produced, or rules fired. A stage firing 23 rules took 12.6s; a stage firing zero rules
took 13.5s; deriving 57M tuples at startup took 72s, which is ~1.3 µs per firing against
~550 ms per firing for the small query.

It is real computation — ~95 CPU-seconds per stage at 6–8× CPU-to-wall, so roughly 40 of
the 47 workers are spinning on barriers while something serial proceeds. The daemon places
it inside the fixpoint, via `$stat_fixpoint`. Typically 2 iterations per stage: one to do
the work, one to observe that nothing new appeared.

Two constraints that are awkward together: the cost **vanishes** on a small database (four
stages on `kg2_sample` cost the same as one), yet **does not scale** with resident size —
deleting `edge_dir` and `edge_rel`, 114M tuples and 20 GB, moved it from 13.3s to 13.4s.

The lead in the slog source: `finalizeAll()` and `reorgAll()` in `daemon/database.h` run at
every iteration boundary as loops over `rel_registry` — every relation in the database, not
only those the rules mention. Right shape, but it predicts that removing relations should
help, and it did not.

One untested hypothesis that fits both constraints: trimming those views removed tuples but
not *vocabulary* — the string dictionary was unchanged, because those views were built from
strings already present. A cost tied to distinct values rather than rows would be invisible
to that experiment, and `kg2_sample`'s dictionary is 425 KB against 2 GB here. Testing it
means building one database with many tuples and few distinct strings, and another with the
reverse.

## Storage

```
data/db/dataTest4         9.8 GB on disk  ->  ~167 GB resident
data/import_ready         17 GB   regenerable, input to csv2db
data/source               4.9 GB  re-downloadable (RTX-KG2 2.8.1)
```

`slog/data/dataTest4` is a **symlink** to `data/db/dataTest4` (same for `dataTest3` and
`kg2norm`). A fresh checkout must recreate those symlinks; slog resolves `data/` relative
to its own root.

Every stage of the data is derived from the public RTX-KG2 download, so nothing here needs
archiving for correctness — only to avoid a multi-hour rebuild.

The ~17× expansion from disk to RAM is index structure, not data. On disk each value is an
interned 8-byte integer stored flat: `kg2_edges` is exactly
`56,965,146 × 15 × 8 = 6,835,817,520` bytes. In memory each relation is held as a B-tree
per ordering it is queried by, plus delta indices for semi-naive evaluation, plus per-worker
send and reorg buffers for every relation across all 47 threads, plus the string dictionary
as a two-way map. One data point: removing 3.65 GB of raw tuples freed 20 GB of RAM.

The database is on NFS, which is why startup reads 9.8 GB at ~25 MB/s. Moving it to
`/local` or `/scratch` should help.

Startup measured 420–535s, and `setup.slog` accounts for roughly two to three minutes of
it, deriving ~182M tuples across four views. `slog_server.rkt` loads the session **before**
opening the port, so no query ever absorbs the load; a connection refused on 8642 means the
server is still loading or was never started. `ensure-session!` is wrapped in `void` there
because a module-level expression in `#lang racket` prints its value, and the session struct
is large.

## Instrumentation

```
logs/<YYYYMMDD-HHMMSS>/
    mcp.log                     narrative, one line per step
    summary.csv                 one row per tool call
    queries/NNN_run_slog.slog   the exact program that ran, numbered by CSV `seq`
```

Nothing is ever written to **stdout** — FastMCP speaks JSON-RPC over it, and a stray print
corrupts the protocol. All logging goes to the session file and to stderr.

`slog/query.slog` is overwritten on every edit, so `queries/NNN_run_slog.slog` is the only
record of what each individual run executed. Two runs can be diffed directly.

### Where each CSV column comes from

Trust them in this order.

**The daemon's own accounting** — `n_strata_executed`, `iterations`, `fixpoint_ms`,
`rule_fires`. Read from two daemon-owned relations. `$stat_fixpoint` gets one row per
stratum: `(push position, stratum hash, iterations, microseconds)`. `$stat_fires` counts
rule instantiations as `(rule location, variant, count)`. Both accumulate for the life of
the session, so a single run's contribution is a delta: positions increase monotonically,
so rows above the previous high-water mark belong to the run that just finished. `SLOG_NO_STATS=1`
would disable publication.

`rule_fires` is the diagnostic to reach for. A large `fixpoint_ms` with a tiny `rule_fires`
means the time went to overhead rather than computation.

**Python's stopwatch** — `wall_s`, `drop_s`, `run_s`, `dump_s`. Honest wall clock, but from
outside; they measure waiting, not work. `run_s` covers compile *and* execution, because the
`run` verb does both. `dump_s` scales with `n_rows` rather than `returned`, because the
daemon streams and counts every tuple even though only 500 come back.

**The filesystem** — `n_strata_compiled` and `compile_s`, from the `.cpp` and `.O0.so`
files clang leaves in the slog build directory. Indirect. `compile_s` deliberately measures
to the newest `.O0.so`, **not** the newest `.so`: under `SLOG_OPT=tiered` the plain `.so` is
the detached `-O2` build that never blocked the query, and charging its link time inflates
compile while deflating `exec_s` by the same amount. `SLOG_OPT=2` is the case where the
`-O2` artifact is the blocking one.

**Arithmetic** — `exec_s` (`run_s − compile_s`), `predicted_s`
(`COMPILE_S + PER_STRATUM_S × n_derived_rels`), `cost_ratio` (`wall_s / predicted_s`).
Sort by `cost_ratio` to find anomalies; ~1.0 means the query cost what its shape implies.
`n_derived_rels` is parsed from the program text and slightly over-counts, since slog fuses
some stages — `n_strata_executed` is authoritative but only available after the run.

Ordering constraint in `run_slog`: the stats and build snapshots are taken **after** the
drop, never before. The drop is the first slog call, so on a cold session it is the request
that opens the session; snapshotting earlier would make a diagnostic dump trigger and
absorb the multi-minute load.

## kg2_edges / kg2_nodes column map

`setup.slog` matches these by position with bare wildcards and explains none of them. This
block is otherwise recorded only in an untracked file inside the slog clone.

```
kg2_edges, in order:
   1 core_predicate   2 knowledge_source   3 negated    4 :END_ID
   5 predicate_label  6 qualified_object_aspect         7 qualified_object_direction
   8 qualified_predicate                   9 relation_label   10 source_predicate
  11 :START_ID       12 update_date       13 predicate:TYPE  14 subject   15 object

kg2_nodes, in order:
   1 :LABEL           2 category_label     3 creation_date   4 deprecated
   5 full_name        6 has_biological_sequence             7 id:ID
   8 iri              9 knowledge_source  10 name           11 replaced_by
  12 update_date     13 category
```

`kg2_node_synonym` and `kg2_node_publication` are keyed on the node id, `kg2_nodes` column 7.

So `edge` keeps columns 14, 1, 15 and filters on column 3 being `"False"`, which is why
negated edges never reach a query. `edge_dir` adds 6 and 7. `edge_rel` takes 13, the
source-specific predicate, instead of 1, the normalized biolink one. `node` takes 7, 10, 13.
