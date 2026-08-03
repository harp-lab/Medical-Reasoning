# RTX-KG2 query guide

RTX-KG2 is a biomedical knowledge graph queried with Soufflé Datalog. The whole graph is
one edge relation:

    edge(subj, pred, obj, neg)

- `subj`, `obj` — CURIEs, e.g. `MONDO:0005180`
- `pred` — a biolink predicate, e.g. `biolink:treats`
- `neg` — `"True"` / `"False"`; use only `neg="False"` (asserted, non-negated edges)

## Workflow

1. **`list_predicates()`** — the valid predicates; pick the relevant one(s).
2. **`resolve_entity(term)`** for each named entity (drug, disease, gene, …).
   If several plausible senses come back (different biolink types, or unrelated concepts),
   **stop and ask the user which they mean** — only auto-proceed on a single clear match.
   Use `search_nodes(term)` if `resolve_entity` comes back empty.
3. **`expand_entity([chosen CURIEs])`** → the exact KG2 CURIE set to match in the query.
4. **Write a Soufflé program** (conventions below).
5. **`run_datalog(program)`** to execute it.
6. **`name_curies([result CURIEs])`** → human-readable labels.

## Writing the Datalog

- The `edge` relation is loaded for you — reference `edge(subj, pred, obj, neg)` directly.
  (You may declare it yourself instead; the server prepends these two lines if you don't:)

      .decl edge(subj:symbol, pred:symbol, obj:symbol, neg:symbol)
      .input edge(IO=file, filename="rtx-kg2_edges_2.8.1.tsv", columns="16:0:17:3")

- Bind each entity as a membership relation over the exact CURIEs from `expand_entity`:

      .decl drug_set(x:symbol)
      drug_set("CHEBI:6801"). drug_set("...").

- Predicates are exact quoted strings from `list_predicates()`, e.g. `"biolink:treats"`.
- Use only `neg="False"`.
- Multi-hop joins and recursion are allowed. Use lowercase relation names; avoid the
  built-in name `cat`.
- The final answer relation **must** be named `result`; end with `.output result`.

## Performance

Each `run_datalog` re-scans the ~38 GB edge file (~90 s; compute itself is sub-second).
Prefer one well-formed query over many exploratory runs.
