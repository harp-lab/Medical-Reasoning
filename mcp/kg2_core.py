"""RTX-KG2 query core: NCATS entity grounding, predicate lists, and result naming.

Pure, non-interactive helpers backing the kg2 MCP server (ported from all_souffle.ipynb).
Diagnostics go to stderr only — stdout carries the MCP JSON-RPC stream.

Query execution lives elsewhere: slog_client talks to the resident Slog session
(slog/slog_server.rkt). This module is engine-agnostic.

Paths come from the environment (KG2_DATA_DIR, KG2_PREDICATES_TSV), defaulting to
this repo.
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

# Project root is the parent of this mcp/ package.
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("KG2_DATA_DIR", os.path.join(PROJECT_DIR, "data"))
PREDICATES_TSV = os.environ.get(
    "KG2_PREDICATES_TSV", os.path.join(DATA_DIR, "reference", "distinct_core_predicate.tsv"))

# The original 16-column node export; column 8 (1-based) is id:ID.
NODES_TSV = os.path.join("source", "rtx-kg2_nodes_2.8.1.tsv")


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


def kg2_has_ids(ids):
    """Subset of `ids` present in KG2, via the indexed node table."""
    ids = [str(i) for i in ids if str(i)]
    if not ids:
        return set()
    conn = _node_db()
    found = set()
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        q = f"SELECT id FROM nodes WHERE id IN ({','.join('?' * len(chunk))})"
        found.update(r[0] for r in conn.execute(q, chunk))
    return found


def expand_to_kg2(curie):
    """NodeNorm clique intersected with KG2 node ids -> (kept, full_clique)."""
    clique = nodenorm_clique(curie)["equivalent_ids"]
    present = kg2_has_ids(list(clique) + [curie])
    kept = [c for c in clique if c in present]
    if curie in present and curie not in kept:
        kept.append(curie)
    return kept, clique


# --- node lookup index --------------------------------------------------------
# Naming and substring search do not go through the query engine.  Slog has no
# regex primitive, so substring search cannot be a Slog rule, and baking a
# per-call id list into a program means a fresh clang build every time.
#
# Scanning the 4.9 GB node export per call costs ~105s (it is on NFS), so instead
# we build a small SQLite index once and query that: naming becomes an indexed
# lookup, substring search a ~2s local scan.  It lives on local NVMe because
# SQLite over NFS is a locking hazard; losing it just means one rebuild.
#
# Column numbers are 1-based into the ORIGINAL 16-column node export:
#   8 = id:ID, 11 = name, 14 = synonym, 16 = category
_NODE_ID_COL, _NODE_NAME_COL, _NODE_SYN_COL, _NODE_CAT_COL = 8, 11, 14, 16

NODE_DB = os.environ.get(
    "KG2_NODE_DB",
    os.path.join(tempfile.gettempdir(), f"kg2_nodes_{os.environ.get('USER','u')}.sqlite"))

_node_conn = None


def _build_node_db(path):
    """One pass over the node export -> indexed (id, name, category, syn) table."""
    t0 = time.perf_counter()
    tmp = path + ".building"
    if os.path.exists(tmp):
        os.remove(tmp)
    conn = sqlite3.connect(tmp)
    conn.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;")
    conn.execute("CREATE TABLE nodes (id TEXT, name TEXT, category TEXT, syn TEXT)")
    cut = subprocess.Popen(
        ["cut", "-f", f"{_NODE_ID_COL},{_NODE_NAME_COL},{_NODE_SYN_COL},{_NODE_CAT_COL}",
         os.path.join(DATA_DIR, NODES_TSV)],
        stdout=subprocess.PIPE, text=True, bufsize=1 << 20)

    def rows():
        # cut emits fields in ascending column order: id, name, syn, category
        for line in cut.stdout:
            f = line.rstrip("\n").split("\t")
            if len(f) >= 4:
                yield (f[0], f[1], f[3], f[2])

    conn.executemany("INSERT INTO nodes VALUES (?,?,?,?)", rows())
    cut.wait()
    # non-unique: a duplicate id in the export must not fail the whole build
    conn.execute("CREATE INDEX IF NOT EXISTS nodes_id ON nodes(id)")
    conn.commit()
    conn.close()
    os.replace(tmp, path)
    _log(f"[node db] built {path} in {time.perf_counter()-t0:.0f}s")


def _node_db():
    global _node_conn
    if _node_conn is None:
        if not os.path.exists(NODE_DB):
            _log(f"[node db] {NODE_DB} missing; building once (~2 min)")
            _build_node_db(NODE_DB)
        _node_conn = sqlite3.connect(NODE_DB, check_same_thread=False)
    return _node_conn


def _match_rank(name, term_lc):
    nl = name.lower()
    return 0 if nl == term_lc else 1 if nl.startswith(term_lc) else 2 if term_lc in nl else 3


def search_nodes(term, limit=25):
    """Case-insensitive substring search over node names and synonyms.

    Fallback for terms NameRes misses.  LIKE '%term%' cannot use an index, so this
    is a scan -- but a local one, a couple of seconds rather than a couple of minutes.
    """
    term_lc = term.strip().lower()
    if not term_lc:
        return []
    t0 = time.perf_counter()
    # escape LIKE wildcards so a term containing % or _ is matched literally
    esc = term_lc.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pat = f"%{esc}%"
    rows = _node_db().execute(
        "SELECT id, name, category FROM nodes "
        "WHERE lower(name) LIKE ? ESCAPE '\\' OR lower(syn) LIKE ? ESCAPE '\\' "
        "LIMIT 5000", (pat, pat)).fetchall()
    _log(f"[search_nodes] {len(rows)} hits for {term!r} in {time.perf_counter()-t0:.1f}s")
    if not rows:
        return []
    df = pd.DataFrame(rows, columns=["id", "name", "category"]).fillna("")
    df["rank"] = df["name"].map(lambda n: _match_rank(n, term_lc))
    df["nlen"] = df["name"].str.len()
    df = df.sort_values(["rank", "nlen"]).drop_duplicates("id").head(limit)
    return df[["id", "name", "category"]].to_dict("records")


def resolve_term(term, limit=10, biolink_type=None):
    """NameRes concept lookup, falling back to substring search when NameRes is empty.

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
    """Map result CURIEs -> [{id, name, category}] by indexed lookup."""
    ids = [str(c) for c in curies if str(c)]
    if not ids:
        return []
    t0 = time.perf_counter()
    conn = _node_db()
    out = []
    # chunked so a large result set stays inside SQLite's parameter limit
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        q = f"SELECT id, name, category FROM nodes WHERE id IN ({','.join('?' * len(chunk))})"
        out.extend(conn.execute(q, chunk).fetchall())
    _log(f"[name_curies] named {len(out)}/{len(ids)} in {time.perf_counter()-t0:.2f}s")
    return [{"id": r[0], "name": r[1] or "", "category": r[2] or ""} for r in out]
