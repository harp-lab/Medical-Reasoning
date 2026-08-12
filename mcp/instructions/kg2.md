# RTX-KG2 query guide

RTX-KG2 is a biomedical knowledge graph queried with **Slog**, a Datalog dialect. The
graph is already loaded in a resident session, so queries cost a compile (a few seconds),
not a reload.

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

## Writing the Slog

Syntax is `rule (head) <-- (body goals)`. Body goals are listed with no commas. `_` is a
wildcard.

**Every relation must be declared with `table`, including ones you derive and ones the
session already has.** This is the most common mistake.

**The answer relation must be declared and named `result`.** It is dropped before each
run, so it always starts empty.

Bind each entity as a membership relation over the exact CURIEs from `expand_entity`:

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

## Practical notes

- Results are capped at 500 rows; `n_rows` tells you the true count.
- Do not query `kg2_edges` when `edge` will do — the views are much cheaper.
- **Always bind at least one constant** (a predicate or a CURIE) in a rule over `edge`,
  `node` or `kg2_norm`. A rule with only variables scans tens of millions of rows.
- The first `run_slog` of a session takes several minutes to load the KG.
- A warning about an "unkeyed co-recursive scan" means a rule rereads a whole relation
  each iteration because nothing was bound at that join point. Bind a key earlier or
  split the rule.
