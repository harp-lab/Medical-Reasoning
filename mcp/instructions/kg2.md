# RTX-KG2 query guide

RTX-KG2 is a biomedical knowledge graph queried with **Slog**, a Datalog dialect. The
graph is already loaded in a resident session, so a query costs a compile plus evaluation,
not a reload. Read "What a query costs" below before writing rules -- the cost is driven
almost entirely by how you structure the program, and not at all by how much data it
touches.

## The relations you query

```
edge(subj, pred, obj)                        asserted, non-negated edges
edge_dir(subj, pred, obj, aspect, direction) same, plus the qualifier columns
edge_rel(subj, ptype, obj)                   source-specific predicate, e.g. GO:...
node(id, name, category)                     id -> readable name
kg2_norm(kg2_id, preferred_id)               kg2 id -> its canonical CURIE
```

- `subj`, `obj` — CURIEs, e.g. `MONDO:0005180`
- `pred` — a biolink predicate, e.g. `biolink:treats`, from `list_predicates()`
- `direction` — for up/down-regulation questions, e.g. `"upregulated"`
- Negated edges are already excluded; there is no `neg` column to filter.

`kg2_edges` (15 columns) and `kg2_nodes` (13 columns) are also live if you need a column
the views omit.

## Workflow

1. **`list_predicates()`** — the valid predicates; pick the relevant one(s).
2. **`resolve_entity(term)`** for each named entity (drug, disease, gene, …).
   If several plausible senses come back, **stop and ask the user which they mean** —
   only auto-proceed on a single clear match.
3. **`expand_entity([chosen CURIEs])`** → the exact KG2 CURIE set to match in the query.
4. **Write your Slog program to `slog/query.slog`** using Write or Edit (conventions
   below). This file is the program that runs — there is no other place to put it.
5. **`run_slog()`** to execute it. It takes no program argument; it runs whatever is
   currently in `slog/query.slog`. To change the query, edit the file and call it again.
6. **`name_curies([result CURIEs])`** → human-readable labels.

## What a query costs

Measured on this deployment:

```
total  ~=  ~9s compile      (paid whenever the program text changes at all)
       +  ~13s per derived relation
```

A "derived relation" is any relation you declare and fill with a rule -- every `table` you
introduce beyond `result`. The engine must finish and store each one before anything can
read it, and each of those stopping points costs ~13 seconds of fixed bookkeeping.

**What is free.** How much data you touch. A rule over `biolink:affects` (4.7M edges,
166k results) costs the same as one over `biolink:directly_physically_interacts_with`
(12k edges, 5k results) -- both ~13s. Do not narrow a predicate, add a filter, or restrict
a scan for speed. It buys nothing. Ask the question you actually mean.

**What is expensive.** Extra stages. Two hops written as one rule ran in 10.7s warm /
23.7s cold. The same two hops split through one intermediate relation cost 27s. A query
with four intermediates cost 78s.

So **inline aggressively**. Prefer one rule with a longer body over several rules chained
through named relations:

```slog
;; SLOW -- two derived relations, ~13s each
table (hop1 str)
rule (hop1 g)   <-- (met m) (edge m "biolink:interacts_with" g)
rule (result d) <-- (hop1 g) (edge g "biolink:gene_associated_with_condition" d)

;; FAST -- one derived relation, same joins, same answer
rule (result d) <--
  (met m)
  (edge m "biolink:interacts_with" g)
  (edge g "biolink:gene_associated_with_condition" d)
```

**A CURIE set is a stage too.** Collecting anchor CURIEs into a membership relation costs a
full ~13s even though it does no real work. For a handful of CURIEs, write one rule per
CURIE with the CURIE as a literal, all with the same head -- many rules writing one
relation are still a single stage:

```slog
;; SLOW -- pd_set is a second stage (measured 36.4s)
table (pd_set str)
rule (pd_set "MONDO:0005180")
rule (pd_set "DOID:14330")
rule (result name) <-- (pd_set d) (edge drug "biolink:treats" d) (node drug name _)

;; FAST -- one stage, same 1569 answers (measured 25.1s)
rule (result name) <-- (edge drug "biolink:treats" "MONDO:0005180") (node drug name _)
rule (result name) <-- (edge drug "biolink:treats" "DOID:14330")    (node drug name _)
```

Above roughly ten CURIEs the repetition stops paying -- keep the membership relation and
accept the one stage rather than emitting a hundred rules.

**Decide on names before you run, not after.** Running a query that returns bare CURIEs
and then editing it to add `node` costs a second full compile and execution -- ~30s for
nothing. Choose up front:

- want readable output? declare `table (node str str str)` in the first version and join
  `(node x name _)` in the rule. `node` is a base view, so this adds no stage.
- happy with ids? return them and call `name_curies` on the results, which takes
  milliseconds.

Either is fine. Re-running the query purely to add naming is the mistake.

Because every edit recompiles, getting the program right on the first attempt is worth
more than iterating quickly. Re-read the rules below before running.

## Writing the Slog

Syntax is `rule (head) <-- (body goals)`. Body goals are listed with no commas. `_` is a
wildcard.

**Comments start with `;;`, not `;`.** A single semicolon is a syntax error — it fails
with the unhelpful message `End of file expected.`, and the echoed lines point at the top
of the file rather than the offending comment.

**Every relation must be declared with `table`, including ones you derive and ones the
session already has.** This is the most common mistake.

**The answer relation must be declared and named `result`.** It is dropped before each
run, so it always starts empty.

For an entity with more than about ten CURIEs from `expand_entity`, bind them as a
membership relation and accept the one extra stage. Below that, inline them as literals
instead — see "A CURIE set is a stage too". Never derive a set of *predicates* this way;
write those as literals in the rule body:

```slog
table (edge str str str)
table (drug_set str)
table (result str)

rule (drug_set "CHEBI:6801")
rule (drug_set "CHEBI:1234")

rule (result disease) <--
  (drug_set d)
  (edge d "biolink:treats" disease)
```

A direction-sensitive query uses `edge_dir`:

```slog
table (edge_dir str str str str str)
table (result str str)

rule (result g o) <--
  (edge_dir g "biolink:affects" o _ "upregulated")
```

Recursion is allowed and is where Slog earns its keep:

```slog
table (edge str str str)
table (reach str)
table (result str)

rule (reach "MONDO:0005180")
rule (reach y) <-- (reach x) (edge x "biolink:related_to" y)
rule (result x) <-- (reach x)
```

## Joining derived entity sets -- read this

KG2 does not merge equivalent entities. The same gene is a separate node per source
vocabulary: `NCBIGene:6622`, `UniProtKB:P37840` and `HGNC:11138` are all SNCA.

So joining two independently-derived sets on the raw id **silently returns zero rows**,
which looks like "no such entities" but actually means "your keys are from different
vocabularies". Join on the canonical key from `kg2_norm` instead:

```slog
;; WRONG -- returns 0 even when the biology overlaps
rule (result g) <-- (gene_pd g) (tremor_gene g)

;; RIGHT -- both sides mapped to their canonical CURIE, then joined on it
table (kg2_norm str str)
rule (result k) <-- (gene_pd g) (kg2_norm g k) (tremor_gene t) (kg2_norm t k)
```

`kg2_norm` is a precomputed NodeNormalizer mapping over all 11.3M nodes. About a third
of them map to a different CURIE than their own. An id NodeNorm could not resolve maps
to itself, so joining through it never silently drops rows.

**Counting.** Count distinct canonical keys, not raw ids — the same entity appears once
per vocabulary, so counting ids over-counts.

**Naming results.** `name_curies` resolves KG2 node ids, and a canonical key is not
guaranteed to be one. Return a real KG2 id alongside the key:

```slog
rule (result g k) <-- (gene_pd g) (kg2_norm g k) (tremor_gene t) (kg2_norm t k)
```

Single-hop queries against `edge` are unaffected; this only matters when you join two
sets you derived separately. `expand_entity` already handles the CURIEs you put *into* a
query -- `kg2_norm` is for the ones the query produces.

## Reporting the answer -- read this

Report the query output and nothing else. A table of two columns, the CURIE and its
resolved name, in the order Slog returned the rows:

```
| CURIE          | name              |
|----------------|-------------------|
| CHEBI:6801     | metformin         |
| CHEBI:4911     | etoposide         |
```

To have both columns, return the id from the query and resolve the names -- either carry
the name out of the query with `(node x name _)` and return `(result x name)`, or return
ids and call `name_curies`. Never return names alone; the CURIE is the identifier and must
be shown.

Do **not** write:

- any explanation of what the query did, or which relations or predicates were used
- any commentary on the entities -- what a drug is for, why a result is plausible or
  surprising, which ones look like noise
- any summary sentence before or after the table
- caveats about knowledge-graph coverage, or suggested follow-up questions
- the Slog program itself (it is already saved in the log)

Two terse exceptions, because omitting them would misrepresent the result. Give them as a
single line above the table, not as prose:

- truncated: `1627 rows, showing 500`
- empty: `0 rows`

If the user asks for an explanation, give one then. Unasked, the table is the whole answer.

## Practical notes

- Results are capped at 500 rows; `n_rows` tells you the true count.
- Prefer `edge` over `kg2_edges` for readability, not for speed — scan size does not
  affect runtime here.
- The session is loaded before it accepts connections, so no query pays the load. If
  `run_slog` reports that no Slog session server is reachable, the server is either still
  loading or was never started — say so and stop; do not retry in a loop.
- **Never split a rule to make it faster.** Splitting adds a derived relation, which adds
  ~13s. If a rule feels expensive, the fix is fewer stages, not more.
- A returned row count of 0 usually means a join across vocabularies (see above), not an
  expensive query — check `kg2_norm` before rewriting for performance.
