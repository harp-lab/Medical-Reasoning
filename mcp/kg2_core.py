import csv
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("KG2_DATA_DIR", os.path.join(PROJECT_DIR, "data"))
PREDICATES_TSV = os.environ.get(
    "KG2_PREDICATES_TSV",
    os.path.join(DATA_DIR, "reference", "distinct_core_predicate.tsv"))
NODES_TSV = os.path.join(DATA_DIR, "source", "rtx-kg2_nodes_2.8.1.tsv")

NAMERES_URL = "https://name-resolution-sri.renci.org/lookup"
NODENORM_URL = "https://nodenormalization-sri.renci.org/get_normalized_nodes"

NODE_ID_COL, NODE_NAME_COL, NODE_CAT_COL = 8, 11, 16

NODE_DB = os.environ.get(
    "KG2_NODE_DB",
    os.path.join(tempfile.gettempdir(), f"kg2_nodes_{os.environ.get('USER','u')}.sqlite"))

_node_conn = None


def _log(msg):
    print(msg, file=sys.stderr, flush=True)


def load_predicates():
    rows = []
    with open(PREDICATES_TSV) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            rows.append((int(row["n"]), row["predicate"]))
    rows.sort(reverse=True)
    return [p for _, p in rows]


def _get_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def resolve_term(term, limit=10, biolink_type=None):
    params = {"string": term, "limit": limit}
    if biolink_type:
        params["biolink_type"] = biolink_type
    res = _get_json(f"{NAMERES_URL}?{urllib.parse.urlencode(params)}")
    return [{"id": x.get("curie"),
             "name": x.get("label") or "",
             "category": (x.get("types") or [""])[0],
             "score": round(x.get("score") or 0, 1)}
            for x in res]


def nodenorm_clique(curie):
    params = {"curie": curie, "conflate": "true", "drug_chemical_conflate": "true"}
    node = {}
    try:
        node = _get_json(f"{NODENORM_URL}?{urllib.parse.urlencode(params)}").get(curie) or {}
    except Exception as e:
        _log(f"[nodenorm error] {e!r}")
    eqids = [e["identifier"] for e in node.get("equivalent_identifiers", [])
             if e.get("identifier")]
    return list(dict.fromkeys(eqids)) or [curie]


def expand_to_kg2(curie):
    clique = nodenorm_clique(curie)
    present = _kg2_has_ids(list(clique) + [curie])
    kept = [c for c in clique if c in present]
    if curie in present and curie not in kept:
        kept.append(curie)
    return kept


def _build_node_db(path):
    tmp = path + ".building"
    if os.path.exists(tmp):
        os.remove(tmp)
    conn = sqlite3.connect(tmp)
    conn.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;")
    conn.execute("CREATE TABLE nodes (id TEXT, name TEXT, category TEXT)")
    cut = subprocess.Popen(
        ["cut", "-f", f"{NODE_ID_COL},{NODE_NAME_COL},{NODE_CAT_COL}", NODES_TSV],
        stdout=subprocess.PIPE, text=True, bufsize=1 << 20)

    def rows():
        for line in cut.stdout:
            f = line.rstrip("\n").split("\t")
            if len(f) >= 3:
                yield (f[0], f[1], f[2])

    conn.executemany("INSERT INTO nodes VALUES (?,?,?)", rows())
    cut.wait()
    conn.execute("CREATE INDEX IF NOT EXISTS nodes_id ON nodes(id)")
    conn.commit()
    conn.close()
    os.replace(tmp, path)


def _node_db():
    global _node_conn
    if _node_conn is None:
        if not os.path.exists(NODE_DB):
            _log(f"[node db] {NODE_DB} missing; building once (~2 min)")
            _build_node_db(NODE_DB)
            _log("[node db] built")
        _node_conn = sqlite3.connect(NODE_DB, check_same_thread=False)
    return _node_conn


def _kg2_has_ids(ids):
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


def name_curies(curies):
    ids = [str(c) for c in curies if str(c)]
    if not ids:
        return []
    conn = _node_db()
    out = []
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        q = f"SELECT id, name, category FROM nodes WHERE id IN ({','.join('?' * len(chunk))})"
        out.extend(conn.execute(q, chunk).fetchall())
    return [{"id": r[0], "name": r[1] or "", "category": r[2] or ""} for r in out]
