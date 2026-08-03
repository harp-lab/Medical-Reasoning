"""RTX-KG2 query core: Soufflé execution, NCATS entity grounding, and result naming.

Pure, non-interactive helpers backing the kg2 MCP server (ported from all_souffle.ipynb).
Diagnostics go to stderr only — stdout carries the MCP JSON-RPC stream.

Paths come from the environment (KG2_DATA_DIR, SOUFFLE_BIN, KG2_OUT_DIR,
KG2_PREDICATES_TSV), defaulting to this repo.
"""
import csv
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

# Project root is the parent of this mcp/ package.
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("KG2_DATA_DIR", os.path.join(PROJECT_DIR, "data"))
SOUFFLE_BIN = os.environ.get("SOUFFLE_BIN", "souffle")
OUT_DIR = os.environ.get("KG2_OUT_DIR", os.path.join(PROJECT_DIR, "scratch", "souffle_out"))
PREDICATES_TSV = os.environ.get(
    "KG2_PREDICATES_TSV", os.path.join(DATA_DIR, "reference", "distinct_core_predicate.tsv"))

# Relative to DATA_DIR; souffle resolves them against `-F DATA_DIR`.
NODES_TSV = os.path.join("source", "rtx-kg2_nodes_2.8.1.tsv")
# kg2_edges.18.tsv is the original 18-column 2.8.1 export under its working name;
# its 0-based columns 16/0/17/3 are subject/core_predicate/object/negated, which is
# what the EDGE_HEADER column spec below selects.
EDGES_TSV = os.path.join("interim", "kg2_import", "kg2_edges.18.tsv")

EDGE_HEADER = (
    ".decl edge(subj:symbol, pred:symbol, obj:symbol, neg:symbol)\n"
    f'.input edge(IO=file, filename="{EDGES_TSV}", columns="16:0:17:3")'
)


def _log(msg):
    print(msg, file=sys.stderr, flush=True)


# --- predicates ---------------------------------------------------------------
_predicates = None


def load_predicates():
    """KG2 core biolink predicates, most-frequent first."""
    global _predicates
    if _predicates is None:
        df = pd.read_csv(PREDICATES_TSV, sep="\t").sort_values("n", ascending=False)
        _predicates = df["predicate"].astype(str).tolist()
    return _predicates


# --- Soufflé execution --------------------------------------------------------
def _profile(prof_path, wall):
    """Runtime breakdown from a souffle `-p` profile.json."""
    if not os.path.exists(prof_path):
        return {"relations": [], "compute_s": None, "load_overhead_s": None}
    relations = json.load(open(prof_path))["root"]["program"]["relation"]
    rows, compute = [], 0.0
    for name, info in sorted(relations.items()):
        rt = info.get("runtime", {})
        secs = (rt.get("end", 0) - rt.get("start", 0)) / 1e6
        compute += secs
        rows.append({"relation": name, "seconds": round(secs, 3), "tuples": info.get("num-tuples")})
    return {"relations": rows, "compute_s": round(compute, 3),
            "load_overhead_s": round(max(0.0, wall - compute), 3)}


def run_souffle(program, out_name="result", timeout=None):
    """Run a Soufflé program; return {rows, n_cols, n_rows, wall_s, profile}.

    Invoked by absolute binary path with `-F DATA_DIR` so the relative filenames inside
    programs resolve regardless of cwd.
    """
    os.makedirs(OUT_DIR, exist_ok=True)
    dl_path = os.path.join(OUT_DIR, f"{out_name}.dl")
    prof_path = os.path.join(OUT_DIR, f"{out_name}_profile.json")
    with open(dl_path, "w") as f:
        f.write(program + "\n")

    cmd = (f"ulimit -s unlimited 2>/dev/null || ulimit -s 1048576; exec "
           f"{shlex.quote(SOUFFLE_BIN)} {shlex.quote(dl_path)} "
           f"-F {shlex.quote(DATA_DIR)} -D {shlex.quote(OUT_DIR)} -p {shlex.quote(prof_path)}")
    t0 = time.perf_counter()
    subprocess.run(["bash", "-c", cmd], check=True, timeout=timeout,
                   env={**os.environ, "OMP_STACKSIZE": "1G"})
    wall = time.perf_counter() - t0
    _log(f"[souffle:{out_name}] wall {wall:.1f}s")

    # Soufflé emits a TSV (<name>.csv); convert to JSON and drop the CSV so souffle_out stays JSON-only.
    csv_path = os.path.join(OUT_DIR, f"{out_name}.csv")
    rows = []
    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
        with open(csv_path, newline="") as f:
            rows = list(csv.reader(f, delimiter="\t"))
        os.remove(csv_path)
    with open(os.path.join(OUT_DIR, f"{out_name}.json"), "w") as f:
        json.dump({"out": out_name, "n_rows": len(rows), "rows": rows}, f, indent=2)
    return {"rows": rows, "n_cols": len(rows[0]) if rows else 0, "n_rows": len(rows),
            "wall_s": round(wall, 2), "profile": _profile(prof_path, wall)}


# --- NCATS grounding: NameRes (text->concepts) + NodeNorm (curie->clique) ------
NAMERES_URL = "https://name-resolution-sri.renci.org/lookup"
NODENORM_URL = "https://nodenormalization-sri.renci.org/get_normalized_nodes"
# conflate merges gene<->protein cliques; drug_chemical_conflate merges drug<->chemical.
DRUG_CHEMICAL_CONFLATE = os.environ.get("DRUG_CHEMICAL_CONFLATE", "true").lower() != "false"

_nameres_cache, _nodenorm_cache = {}, {}


def _get_json(url, data=None, method="GET", timeout=40):
    req = urllib.request.Request(url, data=data, method=method, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def nameres_lookup(term, limit=10, biolink_type=None):
    """NameRes: free text -> ranked candidate concepts."""
    key = (term, limit, biolink_type)
    if key in _nameres_cache:
        return _nameres_cache[key]
    params = {"string": term, "limit": limit}
    if biolink_type:
        params["biolink_type"] = biolink_type
    url = f"{NAMERES_URL}?{urllib.parse.urlencode(params)}"
    try:
        res = _get_json(url)
    except urllib.error.HTTPError as e:
        if e.code != 405:
            raise
        res = _get_json(url, data=b"", method="POST")   # older deployments are POST-only
    hits = [{"id": x.get("curie"), "name": x.get("label") or "",
             "category": (x.get("types") or [""])[0],
             "types": x.get("types") or [],
             "score": round(x.get("score") or 0, 1),
             "clique_n": x.get("clique_identifier_count")}
            for x in res]
    _nameres_cache[key] = hits
    return hits


def nodenorm_clique(curie):
    """NodeNorm: a CURIE -> its equivalent-id clique (+ preferred id, categories)."""
    if curie in _nodenorm_cache:
        return _nodenorm_cache[curie]
    params = {"curie": curie, "conflate": "true",
              "drug_chemical_conflate": "true" if DRUG_CHEMICAL_CONFLATE else "false"}
    node = {}
    try:
        node = _get_json(f"{NODENORM_URL}?{urllib.parse.urlencode(params)}").get(curie) or {}
    except Exception as e:
        _log(f"  [nodenorm error] {e!r}")
    eqids = [e["identifier"] for e in node.get("equivalent_identifiers", []) if e.get("identifier")]
    eqids = list(dict.fromkeys(eqids)) or [curie]   # de-dup, preserve order
    res = {"preferred": (node.get("id") or {}).get("identifier", curie),
           "equivalent_ids": eqids, "categories": node.get("type", [])}
    _nodenorm_cache[curie] = res
    return res


# --- local KG2 node-id set (lazy singleton) -----------------------------------
_node_ids = None


def node_ids():
    """~11.3M KG2 node ids; loaded once on first use (~7s), then reused for the process life."""
    global _node_ids
    if _node_ids is None:
        t0 = time.perf_counter()
        proc = subprocess.Popen(["cut", "-f8", os.path.join(DATA_DIR, NODES_TSV)],
                                stdout=subprocess.PIPE, text=True, bufsize=1 << 20)
        _node_ids = {line.rstrip("\n") for line in proc.stdout}
        proc.wait()
        _log(f"[node ids] loaded {len(_node_ids):,} ids in {time.perf_counter() - t0:.1f}s")
    return _node_ids


def expand_to_kg2(curie):
    """NodeNorm clique intersected with local KG2 node ids -> (kept, full_clique)."""
    clique = nodenorm_clique(curie)["equivalent_ids"]
    ids = node_ids()
    kept = [c for c in clique if c in ids]
    if curie in ids and curie not in kept:
        kept.append(curie)
    return kept, clique


# --- entity search / resolution -----------------------------------------------
def _ci_regex(term):
    """Case-insensitive `.*substring.*` regex for Soufflé match()."""
    parts = []
    for ch in term.strip():
        if ch.isalpha():
            parts.append(f"[{ch.lower()}{ch.upper()}]")
        elif ch in '"]^\\':
            parts.append(".")
        else:
            parts.append(f"[{ch}]")
    return ".*" + "".join(parts) + ".*"


def _match_rank(name, term_lc):
    nl = name.lower()
    return 0 if nl == term_lc else 1 if nl.startswith(term_lc) else 2 if term_lc in nl else 3


def search_nodes(term, limit=25):
    """Soufflé match() regex over node names/synonyms -> [{id, name, category}]."""
    pat = _ci_regex(term)
    program = "\n".join([
        ".decl node(id:symbol, name:symbol, category:symbol, syn:symbol)",
        f'.input node(IO=file, filename="{NODES_TSV}", columns="7:10:15:13")',
        ".decl cand(id:symbol, name:symbol, category:symbol, src:symbol)",
        f'cand(i, n, c, "name") :- node(i, n, c, _), match("{pat}", n).',
        f'cand(i, n, c, "syn") :- node(i, n, c, s), match("{pat}", s).',
        ".output cand",
    ])
    res = run_souffle(program, "cand")
    if not res["n_rows"]:
        return []
    df = pd.DataFrame(res["rows"], columns=["id", "name", "category", "src"]).fillna("")
    term_lc = term.strip().lower()
    df["rank"] = df["name"].map(lambda n: _match_rank(n, term_lc))
    df["nlen"] = df["name"].str.len()
    df = df.sort_values(["rank", "nlen"]).drop_duplicates("id").head(limit)
    return df[["id", "name", "category"]].to_dict("records")


def resolve_term(term, limit=10, biolink_type=None):
    """NameRes concept lookup, falling back to Soufflé match() when NameRes is empty.

    Uniform candidates: {id, name, category, types, score, clique_n, source}.
    """
    hits = nameres_lookup(term, limit=limit, biolink_type=biolink_type)
    if hits:
        return [{**h, "source": "nameres"} for h in hits]
    return [{"id": r["id"], "name": r["name"], "category": r["category"],
             "types": [r["category"]] if r["category"] else [],
             "score": None, "clique_n": None, "source": "match"}
            for r in search_nodes(term, limit=limit)]


# --- result naming ------------------------------------------------------------
def name_curies(curies):
    """Map result CURIEs -> [{id, name, category}] via a Soufflé join on the node table."""
    ids = [str(c) for c in curies if str(c)]
    if not ids:
        return []
    program = "\n".join([
        ".decl node(id:symbol, name:symbol, category:symbol)",
        f'.input node(IO=file, filename="{NODES_TSV}", columns="7:10:15")',
        ".decl want(id:symbol)",
        *(f'want("{i}").' for i in ids),
        ".decl named(id:symbol, name:symbol, category:symbol)",
        "named(i, n, c) :- node(i, n, c), want(i).",
        ".output named",
    ])
    rows = run_souffle(program, "named")["rows"]
    return [{"id": r[0], "name": r[1] if len(r) > 1 else "", "category": r[2] if len(r) > 2 else ""}
            for r in rows]
