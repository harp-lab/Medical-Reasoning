"""Generates main.ipynb. Throwaway builder so we don't hand-escape notebook JSON.
Keep cell source free of triple-single-quotes (''') — cells are wrapped in r'''...'''.
"""
import json

cells = []

def md(text):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)})

def code(text):
    cells.append({"cell_type": "code", "execution_count": None, "metadata": {},
                  "outputs": [], "source": text.rstrip("\n").splitlines(keepends=True)})

md("""# MedicalReasoning — natural-language **one-hop** queries over RTX-KG2

Ask any single-hop question: *what drugs treat Parkinson's?*, *what does levodopa treat?*,
*how is levodopa related to Parkinson's?*, *does aspirin treat Parkinson's?*. The LLM handles
language; DuckDB and Soufflé stay deterministic so entities and rules are grounded in the real KG.

```
question ─▶ [LLM] parse into one-hop slots (subject/predicate/object, each bound or free)
          ─▶ [DuckDB] match each bound entity (ranked) ─▶ you pick one, or 'all'
          ─▶ [LLM] write Soufflé .dl ─▶ [Soufflé] scan 38GB edges ─▶ [DuckDB] name results
```

A one-hop query is `edge(S, P, O)` where each slot is FREE (a variable we return) or BOUND. A
BOUND entity is a **set** of equivalent CURIEs (you pick one, or `all`), so the query catches edges
no matter which vocabulary's id they hang off — a lightweight stand-in for node normalization.
Brute force: Soufflé scans the raw edges file directly (no preprocessing).
""")

md("## Setup")

code(r'''import os
import json
import subprocess
import duckdb
import pandas as pd
from dotenv import load_dotenv
import anthropic

pd.set_option("display.max_colwidth", 80)

NODES_PARQUET = "nodes_index.parquet"
EDGES_TSV     = "rtx-kg2_edges_2.8.1.tsv"
PREDICATES_TSV = "distinct_core_predicate.tsv"   # the 61 real core_predicates (from count_predicates.py)

con = duckdb.connect()
con.execute("SET enable_progress_bar=false")

load_dotenv()                                     # reads .env -> APIKEY
client = anthropic.Anthropic(api_key=os.environ["APIKEY"])
MODEL  = "claude-sonnet-4-5"

def llm(system, user, max_tokens=1024):
    msg = client.messages.create(model=MODEL, max_tokens=max_tokens,
                                 system=system, messages=[{"role": "user", "content": user}])
    return msg.content[0].text

def _json(text):
    """Parse the first {...} block out of an LLM reply (tolerates prose / fences)."""
    i, j = text.find("{"), text.rfind("}")
    return json.loads(text[i:j + 1])

def _souffle_code(text):
    """Strip markdown fences from an LLM-written Soufflé program."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1].rsplit("```", 1)[0]
    return t.strip()
''')

md("""## Build the node index (one-time), then load the KG vocabulary

The node index is a small Parquet distilled once from the 4.9 GB nodes file. From it (and the
predicates file) we load the real **predicate** and **category** vocabularies — no hardcoding.""")

code(r'''if not os.path.exists(NODES_PARQUET):
    print("Building node index (one full scan of the 4.9 GB nodes file)...")
    NODES_TSV = "rtx-kg2_nodes_2.8.1.tsv"   # headerless: 7=id 10=name 13=synonym 15=category
    READ_OPTS = ("delim='\t', header=false, quote='', escape='', ALL_VARCHAR=true, "
                 "max_line_size=10000000, strict_mode=false, ignore_errors=true")
    con.execute(f"""
        COPY (SELECT column07 AS id, column10 AS name, lower(column10) AS name_lc,
                     column15 AS category, column13 AS synonyms
              FROM read_csv('{NODES_TSV}', {READ_OPTS})
              WHERE column07 IS NOT NULL AND column10 IS NOT NULL)
        TO '{NODES_PARQUET}' (FORMAT parquet)
    """)

KG2_PREDICATES = con.execute(
    f"SELECT predicate FROM read_csv('{PREDICATES_TSV}', delim='\t', header=true) ORDER BY n DESC"
).df()["predicate"].tolist()
VALID_CATEGORIES = con.execute(
    f"SELECT DISTINCT category FROM '{NODES_PARQUET}' WHERE category IS NOT NULL ORDER BY 1"
).df()["category"].tolist()

n_nodes = con.execute(f"SELECT count(*) FROM '{NODES_PARQUET}'").fetchone()[0]
print(f"{n_nodes:,} nodes | {len(KG2_PREDICATES)} predicates | {len(VALID_CATEGORIES)} categories")
''')

md("""## Step 1 — parse the question into a one-hop slot plan (LLM)

The LLM returns, per slot, either a named entity (with its biolink categories) or `null` (a free
variable), plus the predicate. We inject the real predicate/category vocabularies so it only picks
values that exist in the KG.""")

code(r'''PARSE_SYSTEM = (
    "You convert a natural-language biomedical question into a ONE-HOP knowledge-graph query "
    "over edges of the form (subject)-[predicate]->(object).\n\n"
    "Return ONLY JSON:\n"
    '{\n'
    '  "subject":   {"name": <entity the user named, or null>, "categories": [<biolink category>, ...]},\n'
    '  "predicate": <one biolink predicate, or null>,\n'
    '  "object":    {"name": <entity the user named, or null>, "categories": [<biolink category>, ...]}\n'
    '}\n\n'
    "Rules:\n"
    "- If the user names a specific thing for a slot, put it in \"name\" and give its likely "
    "biolink \"categories\".\n"
    "- If a slot is what the user is ASKING FOR (the unknown), or they say \"any\": \"name\"=null "
    "and \"categories\"=the expected type(s) (or [] if truly anything).\n"
    "- \"predicate\": pick the single best match from this list, or null if the relation is "
    "unconstrained: " + "{predicates}" + ".\n"
    "- Respect direction: biolink:treats goes drug(subject) -> disease(object).\n"
    "- Use ONLY these biolink categories: " + "{categories}" + "."
)

def parse_query(question):
    # .replace (not .format) — PARSE_SYSTEM contains literal JSON braces {...}
    system = (PARSE_SYSTEM
              .replace("{predicates}", ", ".join(KG2_PREDICATES))
              .replace("{categories}", ", ".join(VALID_CATEGORIES)))
    return _json(llm(system, question, max_tokens=400))
''')

md("""## Step 2 — match each *bound* entity, then pick one or `all` (DuckDB)

Ranked match (exact → name-prefix → substring → synonym), so you see related entities, exact first.
You pick one row, or type `all` to use the whole shown list (the `allselections` idea: query every
candidate id at once, so edges are caught regardless of which vocabulary they hang off).""")

code(r'''def resolve_entity(term, categories=None, limit=20):
    """Rank KG2 nodes whose name/synonym matches `term` (case-insensitive), within `categories`
    if given. rank: 0=exact name, 1=name starts with term, 2=term anywhere, 3=synonym only."""
    t = term.strip().lower()
    cat_filter = ""
    if categories:
        cat_filter = "AND category IN (" + ",".join(f"'{c}'" for c in categories) + ")"
    q = f"""
        SELECT id, name, category,
               CASE WHEN name_lc = ?    THEN 0 WHEN name_lc LIKE ? THEN 1
                    WHEN name_lc LIKE ? THEN 2 ELSE 3 END AS rank
        FROM '{NODES_PARQUET}'
        WHERE (name_lc LIKE ? OR lower(coalesce(synonyms, '')) LIKE ?) {cat_filter}
        ORDER BY rank, length(name)
        LIMIT {limit}
    """
    contains, prefix = f"%{t}%", f"{t}%"
    return con.execute(q, [t, prefix, contains, contains, contains]).df()[["id", "name", "category"]]

def pick_set(df, what="match"):
    """Show exact-match candidates; user enters a number for one, or 'all' for the whole set.
    Returns a list of selected rows (dicts), or None if cancelled."""
    df = df.reset_index(drop=True)
    if len(df) == 0:
        print(f"No exact matches for the {what}."); return None
    print(f"Candidates for the {what} (enter a number for one, or 'all'):\n")
    for i, row in df.iterrows():
        print(f"  [{i:>2}] {row['name'][:55]:55s} {row['category']:35s} {row['id']}")
    while True:
        sel = input("\nNumber, 'all', or blank to cancel: ").strip().lower()
        if sel == "":
            return None
        if sel == "all":
            return df.to_dict("records")
        if sel.isdigit() and int(sel) in df.index:
            return [df.loc[int(sel)].to_dict()]
        print("Invalid selection, try again.")
''')

md("""## Step 3 — write the Soufflé `.dl` (LLM)

The LLM writes one rule over the edges file (`columns="16:0:17:3"` = subject, core_predicate,
object, negated). Each BOUND entity becomes a small **membership relation** (its id set); the rule
binds that slot to a variable ranging over the set. FREE slots become variables returned in
`result`.""")

code(r'''EDGE_HEADER = (
    ".decl edge(subj:symbol, pred:symbol, obj:symbol, neg:symbol)\n"
    f'.input edge(IO=file, filename="{EDGES_TSV}", columns="16:0:17:3")'
)

DL_SYSTEM = (
    "You write Soufflé Datalog for ONE-HOP queries over the RTX-KG2 graph.\n"
    "Every program MUST begin with exactly these two lines:\n"
    + EDGE_HEADER + "\n\n"
    "edge(subj, pred, obj, neg) is one KG edge: subj-[pred]->obj are CURIEs; use only neg=\"False\".\n\n"
    "You are given three slots (subject, predicate, object). Each is FREE or BOUND:\n"
    "- A BOUND ENTITY slot comes as a SET of equivalent CURIEs. Declare a membership relation and "
    "bind that slot to a variable ranging over the set, e.g. for subject:\n"
    "      .decl subject_set(x:symbol)\n"
    "      subject_set(\"ID1\"). subject_set(\"ID2\").\n"
    "  then use subject_set(S) in the rule body with S as the subject. Use the EXACT CURIEs given.\n"
    "- A BOUND PREDICATE is just its exact quoted value.\n"
    "- A FREE slot is a capitalized variable.\n\n"
    "Write ONE rule whose head result(...) holds exactly the FREE slot variables, in "
    "subject,predicate,object order. If NO slot is free, use result(\"yes\").\n"
    "Output ONLY the program (no prose/markdown). End with .output result. "
    'lowercase relation names; avoid the built-in "cat".'
)

def _slot_line(role, plan, bindings):
    if role in bindings:
        ids = bindings[role]["ids"]
        idset = ", ".join(f'"{i}"' for i in ids)
        return f'{role}: BOUND to set {{{idset}}}   ({bindings[role]["name"]}, {len(ids)} id(s))'
    cats = plan[role].get("categories") or []
    return f"{role}: FREE variable" + (f"   (type: {', '.join(cats)})" if cats else "")

def generate_dl_llm(question, plan, bindings, out_path="query.dl"):
    pred = plan.get("predicate")
    spec = "\n".join([
        _slot_line("subject", plan, bindings),
        f'predicate: "{pred}"' if pred else "predicate: FREE variable",
        _slot_line("object", plan, bindings),
    ])
    user = f"Question: {question}\n\nOne-hop slots:\n{spec}\n\nWrite the Soufflé program."
    dl = _souffle_code(llm(DL_SYSTEM, user, max_tokens=800))
    with open(out_path, "w") as f:
        f.write(dl + "\n")
    print(f"Wrote {out_path}\n\n{dl}")
    return out_path
''')

md("""## Step 4 — run it over the edges (brute force) and name the results

Soufflé streams the 38 GB edges file into memory once (~2 min, a few GB RAM) and evaluates the
rule; we map the resulting CURIEs back to names + categories via the node index.""")

code(r'''def run_dl(dl_path="query.dl", out_dir="souffle_out"):
    os.makedirs(out_dir, exist_ok=True)
    print(f"Running Soufflé over {EDGES_TSV} (full scan, a few minutes)...")
    subprocess.run(["souffle", dl_path, "-F", ".", "-D", out_dir], check=True)

    out = os.path.join(out_dir, "result.csv")          # .output result -> tab-separated
    rows = pd.read_csv(out, sep="\t", header=None, dtype=str) if os.path.getsize(out) else pd.DataFrame()
    if rows.empty:
        print("No results."); return rows
    ids = rows[0].tolist()                              # first column = the primary answer CURIEs
    idlist = "(" + ",".join(f"'{i}'" for i in ids) + ")"
    named = con.execute(
        f"SELECT id, name, category FROM '{NODES_PARQUET}' WHERE id IN {idlist}"
    ).df()
    print(f"{len(named)} result(s):")
    return named
''')

md("## Run the pipeline")

code(r'''query = input("Ask a one-hop question (e.g. 'what drugs treat parkinson disease?'): ").strip()

plan = parse_query(query)                              # 1. LLM -> slot plan
print("Parsed one-hop plan:\n", json.dumps(plan, indent=2), "\n")

bindings = {}                                          # 2. exact-match + pick one or 'all'
for role in ["subject", "object"]:
    name = plan.get(role, {}).get("name")
    if name:
        rows = pick_set(resolve_entity(name, plan[role].get("categories")), what=role)
        if rows is None:
            raise SystemExit(f"cancelled at {role}")
        bindings[role] = {"name": name, "ids": [r["id"] for r in rows]}
        print(f"  {role}: {len(bindings[role]['ids'])} id(s) selected for '{name}'\n")

generate_dl_llm(query, plan, bindings)                 # 3. LLM writes query.dl (with the id set)
answer = run_dl("query.dl")                            # 4. Soufflé scans edges -> named results
display(answer)
''')

nb = {"cells": cells,
      "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                   "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 5}

with open("main.ipynb", "w") as f:
    json.dump(nb, f, indent=1)
print("wrote main.ipynb:", len(cells), "cells")
