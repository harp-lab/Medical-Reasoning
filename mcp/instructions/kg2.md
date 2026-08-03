# RTX-KG2 query guide

RTX-KG2 is a biomedical knowledge graph queried with **Slog**, a Datalog dialect. The
graph is already loaded in a resident session, so queries cost a compile (a few seconds),
not a reload.

## The relations you query

```
edge(subj, pred, obj)                        asserted, non-negated edges
edge_dir(subj, pred, obj, aspect, direction) same, plus the qualifier columns
node(id, name, category)                     id -> readable name
equiv(id_a, id_b)                            same entity under a different CURIE
```

- `subj`, `obj` — CURIEs, e.g. `MONDO:0005180`
- `pred` — a biolink predicate, e.g. `biolink:treats`, from `list_predicates()`
- `direction` — for up/down-regulation questions, e.g. `"upregulated"`
- Negated edges are already excluded; there is no `neg` column to filter.

`kg2_edges` (15 columns) and `kg2_nodes` (13 columns) are also live if you need a column
the views omit. Call `kg_schema()` for the full list with arities.

## Workflow

1. **`list_predicates()`** — the valid predicates; pick the relevant one(s).
2. **`resolve_entity(term)`** for each named entity (drug, disease, gene, …).
   If several plausible senses come back (different biolink types, or unrelated concepts),
   **stop and ask the user which they mean** — only auto-proceed on a single clear match.
   Use `search_nodes(term)` if `resolve_entity` comes back empty.
3. **`expand_entity([chosen CURIEs])`** → the exact KG2 CURIE set to match in the query.
4. **Write a Slog program** (conventions below).
5. **`run_slog(program)`** to execute it.
6. **`name_curies([result CURIEs])`** → human-readable labels.

## Writing the Slog

Syntax is `rule (head) <-- (body goals)`. Body goals are listed with no commas. `_` is a
wildcard.

**Every relation must be declared with `table`, including ones you derive.** This is the
most common mistake. Declaring a relation the session already has is fine as long as the
arity matches.

**The answer relation must be declared and named `result`.** The server renames it
internally to a content-addressed name, so asking the same question twice reuses the
first answer instead of recomputing it.

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
vocabulary (`NCBIGene:6622`, `UniProtKB:P37840` and `HGNC:11138` are all SNCA), linked
by `same_as` / `close_match` edges.

So joining two independently-derived sets on the raw id **silently returns zero rows**,
which looks like "no such entities" but actually means "your keys are from different
vocabularies". Join through `equiv`:

```slog
;; WRONG -- returns 0 even when the biology overlaps
rule (result g) <-- (gene_pd g) (tremor_gene g)

;; RIGHT
rule (result g) <-- (gene_pd g) (equiv g e) (tremor_gene e)
```

Single-hop queries against `edge` are unaffected; this only matters when you join two
sets you derived separately. `expand_entity` already does this for the CURIEs you put
*into* a query -- `equiv` is for the ones the query produces.

## Reusing earlier work

Relations persist for the life of the session. `kg_schema()` shows what is already
materialised, including results of earlier questions. If a follow-up question builds on
one, reference that relation by name and only the new part is computed.

Prefer decomposing a question into named steps at the level of meaningful concepts
("drugs treating X", "genes upregulated by Y") rather than one monolithic rule. Steps are
individually reusable; a single large rule is not.

## Practical notes

- Programs are validated against the live schema before compiling, so arity and
  undeclared-relation mistakes come back immediately. Read the `problems` list and resubmit.
- Results are capped at 500 rows; `n_rows` tells you the true count.
- Do not query `kg2_edges` when `edge` will do — the views are much cheaper.
- **Always bind at least one constant** (a predicate or a CURIE) in a rule over the base
  relations. A rule with only variables scans tens of millions of rows; it is rejected
  before compiling.
- A relation being live in the session does not exempt you from declaring it: every
  program needs its own `table` line for every relation it mentions.
- `session_status()` tells you whether the session is warm. A cold one takes about six
  minutes and ~97 GB to load.
- A warning about an "unkeyed co-recursive scan" means a rule rereads a whole relation
  each iteration because nothing was bound at that join point. Bind a key earlier or
  split the rule.
