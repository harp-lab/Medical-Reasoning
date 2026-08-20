# KG2 in Slog — status, data layout, and how Slog works

Written 2026-08-02. Everything below was run on `gpu-2024-a100a`.

---

## 1. Short version

The RTX-KG2 knowledge graph is imported into a Slog database called `dataTest3`
and it loads and queries successfully. Four relations, all with exact row counts:

| relation | rows | columns |
|---|---|---|
| `kg2_edges` | 56,965,146 | 15 |
| `kg2_nodes` | 11,342,763 | 13 |
| `kg2_node_synonym` | 15,324,780 | 2 |
| `kg2_node_publication` | 5,347,511 | 2 |

Import took under 40 minutes. The database is 9.6 GB on disk and needs about
**81 GB of RAM** when loaded.

What is verified: the import is complete and correct, the database loads, Slog
reports the right sizes, and a single-rule query runs to fixpoint (~30 seconds
of scanning after the ~5 minute load).

What is not verified: I never got actual result *rows* written to a file, and a
two-rule join against `kg2_nodes` was cut off by a memory limit before it
finished. Details in §7.

---

## 2. Where everything is

**The database** (the thing you query):

```
Projects/MedicalReasoning/data/db/dataTest3/     <- the real files, 9.6 GB
Projects/slog/data/dataTest3                  <- symlink pointing to the above
```

Both paths are the same data. The symlink exists because Slog insists on
finding databases at `./data/<name>` relative to wherever you launch it, and
Slog can only be launched from its own repo (§5.4).

**Helper files I added, in `Projects/slog/`:**

- `kg2-run.sh` — sets up the environment and runs a query. Use this.
- `kg2-decls.slog` — the four `table` declarations plus the full column
  mapping in comments. Paste into any query.
- `kg2query.slog` — a small working example query.

**Inputs used to build it** (on `/tmp`, safe to delete, regenerable):

```
/tmp/aayush.shrestha@ad.wsu.edu/kgwork/in/     <- the quoted TSV files, ~16 GB
/tmp/aayush.shrestha@ad.wsu.edu/kgwork/run/data/dataTest3   <- original build output
```

**The build script:** `MedicalReasoning/pipeline/run_import4.sh`. It does the
preprocessing *and* the import in one pass.

---

## 3. The data

### What we started with

RTX-KG2 version 2.8.1, as TSV:

- `data/interim/kg2_import/kg2_edges.18.tsv` — 40 GB, 18 columns, ~57M rows
- `data/source/rtx-kg2_nodes_2.8.1.tsv` — 16 columns, ~11.3M rows

Column names come from the two header files in `MedicalReasoning/`
(`rtx-kg2_edges_header_2.8.1.tsv`, `rtx-kg2_nodes_header_2.8.1.tsv`).

### Edges: 18 columns in, 15 out

Kept, in this order:

| # | name |
|---|---|
| 1 | `core_predicate` |
| 2 | `knowledge_source` |
| 3 | `negated` |
| 4 | `:END_ID` |
| 5 | `predicate_label` |
| 6 | `qualified_object_aspect` |
| 7 | `qualified_object_direction` |
| 8 | `qualified_predicate` |
| 9 | `relation_label` |
| 10 | `source_predicate` |
| 11 | `:START_ID` |
| 12 | `update_date` |
| 13 | `predicate:TYPE` |
| 14 | `subject` |
| 15 | `object` |

Dropped three:

- **`id`** (original column 2). This is the edge's own identifier, built by
  gluing together subject, predicate, qualifiers, object, and source — e.g.
  `UMLS:C0038838---SEMMEDDB:treats---None---None---None---UMLS:C0085580---SEMMEDDB:`.
  Every piece of it already exists in other columns, so nothing is lost.
  Dropping it is the single biggest reason the import went from 12+ hours to
  40 minutes (§4).
- **`publications`** and **`publications_info`** (original 7 and 8). Long lists
  of PMIDs and a JSON blob. Not needed for reasoning over graph structure.

Note that `subject` and `:START_ID` hold the same value, as do `object` and
`:END_ID`. You could drop two more columns if you wanted.

### Nodes: 16 columns in, 13 out, plus 2 side tables

Kept: `:LABEL`, `category_label`, `creation_date`, `deprecated`, `full_name`,
`has_biological_sequence`, `id:ID`, `iri`, `knowledge_source`, `name`,
`replaced_by`, `update_date`, `category` — in that order, so **column 7 is the
node id** and **column 10 is the name**.

- `description` was dropped — long free text.
- `publications` and `synonym` were pulled out into their own two-column
  tables, keyed on the node id. These were multi-valued fields packed into one
  cell; splitting them makes them joinable.
- `full_name` and `name` were length-trimmed.
- `has_biological_sequence` was **blanked, not truncated**. Truncating a
  chemical structure or protein sequence produces a different, valid-looking
  sequence, which is worse than an empty field.

### Two data problems we had to fix

**Unbalanced parentheses.** Node ids like `ttd.target:Cyano(dimethyl...` come
from IUPAC chemical names and often have an opening paren with no closing one.
About 0.12% of node rows are affected. Slog's TSV reader treats an unquoted `(`
as the start of an s-expression and scans forward across tab delimiters looking
for the match — so an unbalanced paren is a hard error, and a *balanced* one is
worse, because it silently swallows tabs and merges columns. The fix is to wrap
**every** cell in quotes, escaping backslashes and quotes inside. This is not
optional hygiene; unquoted TSV cannot safely carry this data.

**CRLF line endings.** The source files use Windows line endings. Stripping only
`\n` leaves a `\r` stuck on the end of the last column of every row, which then
got preserved inside the quotes. Now stripped explicitly.

---

## 4. Why the first attempts failed

Useful context, because the failures were unrelated to each other.

1. **Attempt 1 (12+ hours, stalled at 44%).** Caused by the `id` column. It was
   unique on all 57M rows, so Slog's string interning table needed 57M separate
   entries for it alone. As that table grew, import throughput decayed from
   3,500 rows/sec to about 700. Removing the column took the rate to **52,000
   rows/sec** — roughly 15x the old peak — and shrank the string table from
   several GB to 149 MB at the equivalent point.

2. **Attempt 2 (parens).** Fixed by quoting every cell.

3. **Attempt 3 (silent truncation).** The quoting step filled the 100 GB home
   quota while writing. The output file was cut off at 53.7M of 57M rows, and
   the importer then choked on a corrupted line. This is the dangerous one — it
   looked like a data problem, not a disk problem. Fixed by moving all work to
   `/tmp` (local NVMe, no quota, and faster than the NFS home).

4. **Attempt 4 — succeeded.** One pass: `cut` the 15 columns straight out of the
   original 40 GB file, strip `\r`, quote every cell, import. No intermediate
   files.

---

## 5. How Slog works

### 5.1 The Datalog part

If you know Datalog, you know most of this. A program declares relations and
rules, and Slog applies the rules until nothing new can be derived — the least
fixpoint. No loops, no mutable state.

Slog's syntax uses `-->` (forwards) or `<--` (backwards):

```slog
table (edge int int)
table (path int int)

rule (edge X Y) --> (path X Y)
rule (path X Y) (edge Y Z) --> (path X Z)
```

Equivalently, `rule (path X Y) <-- (edge X Y)`. Multiple body goals are just
listed; there is no comma. `_` is an anonymous wildcard.

**Every relation must be declared with `table`, including derived ones.** This
is the one thing that will bite you first. Slog does not infer relations from
rules — if you write a rule head for an undeclared relation you get
`Table foo ... is not defined`. That is also why querying our database requires
the four declarations in `kg2-decls.slog`: without them Slog does not know the
on-disk relations exist.

The declaration gives the arity and column types. `str` is a string, `int` an
integer. Our KG is all `str`.

### 5.2 What Slog adds beyond textbook Datalog

- **Compiled and parallel.** Rules are grouped into strata, each stratum is
  compiled to C++, built into a shared library (`.so`), and executed by a
  multithreaded C++ daemon called `slogd`. This is why the toolchain matters so
  much (§5.5) — running a query literally invokes a C++ compiler.
- **Structured values.** Columns can hold nested trees, lists, sets, and maps,
  not just atoms.
- **Demand-driven relations.** A recursive relation can be used like a memoized
  function, computed only for the inputs actually asked for. See `docs/demand.md`.
  Likely relevant for us — it is how you avoid materializing all paths.
- **Lattice relations.** Built-in support for min/max/count/set-valued relations
  that converge, for things like shortest paths. See `docs/lattices.md`.
- **Persistent databases.** A run can save its facts; a later program can load
  or extend them. That is what our import produced.

There is a tutorial at `slog/docs/tutorial` and user docs at `slog/docs/user`.

### 5.3 How a database is stored on disk — the `.bin` question

A Slog database is a **directory of directories**. Ours:

```
data/dataTest3/
  table.kg2_edges.arity.15/0.bin              6519 MB
  table.kg2_nodes.arity.13/0.bin              1125 MB
  table.kg2_node_synonym.arity.2/0.bin         234 MB
  table.kg2_node_publication.arity.2/0.bin      82 MB
  value.strings/0.bin                         1802 MB
```

**One directory per relation.** The directory name encodes the relation name and
its arity: `table.<name>.arity.<N>`. The daemon splits on the *last* `.arity.`,
so relation names containing dots are fine. Arity must be between 1 and 32.

**Every value is exactly 8 bytes.** A row is therefore `arity × 8` bytes with no
delimiters, headers, or padding — a flat array of fixed-width tuples. You can
check this: 56,965,146 rows × 15 columns × 8 bytes = 6519 MB, exactly the size
of the edges file.

Those 8 bytes are a NaN-boxed IEEE-754 double. Real numbers are stored directly;
everything else hides in the unused NaN bit patterns, with tag bits saying
whether the payload is an interned string, a small integer, or a struct. The
practical consequence is that **the tuple files contain no text at all** —
strings appear only as integer ids.

**`value.strings/` is where the text lives.** All 44,792,514 distinct strings in
our KG are stored once here, and every occurrence in every relation is an 8-byte
reference to one of them. This is why the unique-`id` column was so expensive:
it added 57M entries to this table that were never reused. It is also why the
database is only 9.6 GB despite the input TSVs being ~16 GB — repeated values
like `biolink:related_to` are stored exactly once.

**Multiple `.bin` files per relation.** This is your question. The daemon reads
**all** `.bin` (and `.bin.gz`) files inside a relation's directory and unions
them — see `daemon/database.h:7432`. The filenames are just shard indices; the
order is irrelevant, because a relation is a set of tuples, not a sequence. Our
import wrote a single `0.bin` per relation, but when Slog *writes* a database it
can split output across many shards, one per hash bucket, so they can be written
and read in parallel. Nothing needs to be concatenated or merged by hand. To
split a relation yourself you could drop extra `.bin` files into its directory.

The same idea applies on the input side: `csv2db` accepts either one TSV per
relation or a *directory* of shard files per relation.

### 5.4 Slog must run from its own repository

Slog resolves `data/`, `daemon/`, `build/`, and `out/` relative to the current
working directory (`compiler/runslog.rkt:228`). There is no flag to change this.
So you cannot `cd` into `MedicalReasoning` and run Slog there — it will look for
a `daemon/` directory, not find one, and fail.

That is why the database physically lives in `MedicalReasoning/data/` but is
symlinked into `slog/data/`. You run from `slog/`, and it follows the link.

### 5.5 Environment setup that was needed

Four things had to be fixed before anything ran on this machine.

1. **Clang is mandatory.** Slog passes `-ferror-limit` and `-fbracket-depth` to
   the C++ compiler; both are clang-only, so the gcc fallback in the code does
   not actually work. This machine had no clang. Installed clang 22 into a
   dedicated conda environment: `~/miniconda3/envs/slogtc`. Remove with
   `conda env remove -n slogtc` if you ever want it gone.

2. **The daemon must be rebuilt with the same clang** so the daemon and the
   generated plugin `.so`s share one OpenMP runtime. Done:
   `make -C daemon CXX=clang++`. (It was previously unbuilt.)

3. **GMP and Boost headers.** Installed into the base conda env (`gmp`,
   `libboost-headers`). The system had `libgmp.so` but no header, and no root
   access to install one.

4. **The memory cap has to be disabled.** Slog launches the daemon under
   `systemd-run --user --scope` to enforce a memory limit. An SSH session has no
   user D-Bus, so that launch fails and the daemon never starts — the symptom is
   a confusing `Broken pipe`. `SLOG_NO_MEM_CAP=1` launches it directly. The
   default cap of 4 GB is useless here anyway, since loading this KG takes 81 GB.

`kg2-run.sh` sets all of this up.

---

## 6. How to run a query

```bash
/home.na1/ad.wsu.edu/aayush.shrestha/pvt/Projects/slog/kg2-run.sh myquery.slog
```

A query file needs the `table` declarations for both the KG relations and
anything you derive:

```slog
table (kg2_edges str str str str str str str str str str str str str str str)
table (kg2_nodes str str str str str str str str str str str str str)
table (nbr str str)

;; everything one metabolite points at, with the predicate
;; edge col 13 = predicate:TYPE, col 14 = subject, col 15 = object
rule (nbr pred obj) <--
  (kg2_edges _ _ _ _ _ _ _ _ _ _ _ _ pred "HMDB:HMDB0045120" obj)
```

Two warnings:

- **Do not use `--debug-dir`.** It writes one CSV per non-empty relation —
  including all 57M edges, several GB, onto your quota-limited home directory.
  I made this mistake; it is what I had to kill.
- **Expect a ~5 minute load and 81 GB of RAM** before your query starts. The
  node has 503 GB total and is shared.

---

## 7. What is unfinished

**Getting result rows out.** `--sizes` gives you row counts, which is how I
confirmed the import. But the only mechanism I used for actual rows was
`--debug-dir`, which dumps everything. There is a REPL (`./slog`, documented in
`Readme.md` and `docs/repl.md`) that would be the right tool — it also keeps the
database loaded between queries instead of paying 5 minutes and 81 GB each time.
**The `./slog` executable is not present in this checkout.** Worth asking Tom
about; it is probably the single biggest quality-of-life improvement available.

**The two-relation join.** This query:

```slog
rule (nbr_named pred obj nm) <--
  (nbr pred obj)
  (kg2_nodes _ _ _ _ _ _ obj _ _ nm _ _ _)
```

derived 89M tuples and hit a 57.6 GB ceiling before finishing. I raised the
limit to 200 GB but killed the run for unrelated reasons before it completed, so
this is **untested, not known-broken**. 89M intermediate tuples from what should
be a small lookup suggests the join is being evaluated in an unhelpful order —
worth understanding before running it again.

**Whether the column mapping is right in practice.** The mapping in §3 comes
from the header files and is consistent with spot-checked rows, but no query has
yet returned rows we have eyeballed for correctness.

---

## 8. Suggested next steps

1. Get `./slog` (the REPL) working, or find out from Tom how to extract result
   rows without dumping every relation. Everything else is slower until this is
   solved.
2. Run one small query and actually look at the output, to confirm the column
   mapping end to end.
3. Then revisit the join, and read `docs/demand.md` — demand-driven evaluation
   is probably the right tool for path queries over a graph this size.
4. Decide what to do about `/tmp`. It is node-local and can be cleaned without
   warning. The database is safely copied to your home directory, but the 16 GB
   of quoted inputs there are not backed up. They are regenerable from
   `run_import4.sh` in about 5 minutes, so this is probably fine.
5. Consider asking VCEA IT (support.vcea@wsu.edu, cc your PI) for a `/scratch`
   directory. 6.9 TB, no quota, faster than home. It needs sudo to create, which
   you do not have. Contents are deleted every Jan 1 / Jun 1 / Aug 1.
