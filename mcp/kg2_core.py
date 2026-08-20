import csv
import json
import os
import sqlite3
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request

from mr_logging import fmt_dur, get_logger, preview, step

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

log = get_logger("kg2_core")

_http_s = 0.0
_http_calls = 0


def take_http_stats():
    global _http_s, _http_calls
    s, n = round(_http_s, 3), _http_calls
    _http_s, _http_calls = 0.0, 0
    return s, n


def load_predicates():
    t0 = time.perf_counter()
    rows = []
    with open(PREDICATES_TSV) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            rows.append((int(row["n"]), row["predicate"]))
    rows.sort(reverse=True)
    log.info(f"  loaded {len(rows)} predicates from {PREDICATES_TSV} "
             f"in {fmt_dur(time.perf_counter() - t0)}")
    return [p for _, p in rows]


def _get_json(url):
    global _http_s, _http_calls
    host = urllib.parse.urlsplit(url).netloc
    t0 = time.perf_counter()
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            data = json.load(r)
    except Exception as e:
        _http_s += time.perf_counter() - t0
        _http_calls += 1
        log.error(f"  x HTTP {host} failed after {fmt_dur(time.perf_counter() - t0)}: {e!r}")
        raise
    elapsed = time.perf_counter() - t0
    _http_s += elapsed
    _http_calls += 1
    log.info(f"  .. HTTP {host} replied in {fmt_dur(elapsed)}")
    if elapsed > 5:
        log.warning(f"  !! slow remote call to {host} ({fmt_dur(elapsed)})")
    return data


def resolve_term(term, limit=10, biolink_type=None):
    params = {"string": term, "limit": limit}
    if biolink_type:
        params["biolink_type"] = biolink_type
    log.info(f"  name-resolution lookup: term={term!r} limit={limit} "
             f"biolink_type={biolink_type or '(any)'}")
    res = _get_json(f"{NAMERES_URL}?{urllib.parse.urlencode(params)}")
    log.info(f"  name-resolution returned {len(res)} candidate(s)")
    return [{"id": x.get("curie"),
             "name": x.get("label") or "",
             "category": (x.get("types") or [""])[0],
             "score": round(x.get("score") or 0, 1)}
            for x in res]


def nodenorm_clique(curie):
    params = {"curie": curie, "conflate": "true", "drug_chemical_conflate": "true"}
    node = {}
    log.info(f"  node-normalizer clique for {curie}")
    try:
        node = _get_json(f"{NODENORM_URL}?{urllib.parse.urlencode(params)}").get(curie) or {}
    except Exception as e:
        log.warning(f"  !! nodenorm failed for {curie}: {e!r} -- falling back to the "
                    f"bare CURIE, so the expansion will be narrower than intended")
    eqids = [e["identifier"] for e in node.get("equivalent_identifiers", [])
             if e.get("identifier")]
    clique = list(dict.fromkeys(eqids)) or [curie]
    log.info(f"  clique for {curie}: {len(clique)} equivalent id(s) -> {preview(clique)}")
    return clique


def expand_to_kg2(curie):
    t0 = time.perf_counter()
    clique = nodenorm_clique(curie)
    present = _kg2_has_ids(list(clique) + [curie])
    kept = [c for c in clique if c in present]
    if curie in present and curie not in kept:
        kept.append(curie)
    dropped = [c for c in clique if c not in present]
    log.info(f"  expand {curie}: {len(clique)} clique id(s) -> {len(kept)} present in KG2 "
             f"({len(dropped)} not in KG2) in {fmt_dur(time.perf_counter() - t0)}")
    log.info(f"    kept   : {preview(kept)}")
    if dropped:
        log.debug(f"    dropped: {preview(dropped)}")
    if not kept:
        log.warning(f"  !! {curie} expanded to nothing present in KG2 -- any query "
                    f"anchored on it will return no rows")
    return kept


def _build_node_db(path):
    t0 = time.perf_counter()
    log.info(f"  building node DB at {path} from {NODES_TSV}")
    tmp = path + ".building"
    if os.path.exists(tmp):
        log.info(f"  removing stale partial build {tmp}")
        os.remove(tmp)
    conn = sqlite3.connect(tmp)
    conn.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;")
    conn.execute("CREATE TABLE nodes (id TEXT, name TEXT, category TEXT)")
    cut = subprocess.Popen(
        ["cut", "-f", f"{NODE_ID_COL},{NODE_NAME_COL},{NODE_CAT_COL}", NODES_TSV],
        stdout=subprocess.PIPE, text=True, bufsize=1 << 20)

    n = 0

    def rows():
        nonlocal n
        for line in cut.stdout:
            f = line.rstrip("\n").split("\t")
            if len(f) >= 3:
                n += 1
                if n % 1_000_000 == 0:
                    log.info(f"    ... {n:,} nodes inserted "
                             f"({fmt_dur(time.perf_counter() - t0)} elapsed)")
                yield (f[0], f[1], f[2])

    conn.executemany("INSERT INTO nodes VALUES (?,?,?)", rows())
    cut.wait()
    log.info(f"  inserted {n:,} nodes in {fmt_dur(time.perf_counter() - t0)}; indexing")
    with step(log, "CREATE INDEX nodes_id"):
        conn.execute("CREATE INDEX IF NOT EXISTS nodes_id ON nodes(id)")
        conn.commit()
    conn.close()
    os.replace(tmp, path)
    size_mb = os.path.getsize(path) / (1 << 20)
    log.info(f"  node DB ready: {n:,} nodes, {size_mb:.0f} MB, "
             f"total {fmt_dur(time.perf_counter() - t0)}")


def _node_db():
    global _node_conn
    if _node_conn is None:
        if not os.path.exists(NODE_DB):
            log.warning(f"  !! node DB {NODE_DB} missing; building it once "
                        f"(~2 min) -- this call will be slow, later ones will not")
            _build_node_db(NODE_DB)
        else:
            log.info(f"  opening existing node DB {NODE_DB} "
                     f"({os.path.getsize(NODE_DB) / (1 << 20):.0f} MB)")
        _node_conn = sqlite3.connect(NODE_DB, check_same_thread=False)
    return _node_conn


def _kg2_has_ids(ids):
    ids = [str(i) for i in ids if str(i)]
    if not ids:
        return set()
    t0 = time.perf_counter()
    conn = _node_db()
    found = set()
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        q = f"SELECT id FROM nodes WHERE id IN ({','.join('?' * len(chunk))})"
        found.update(r[0] for r in conn.execute(q, chunk))
    log.debug(f"  membership check: {len(found)}/{len(ids)} id(s) present in KG2 "
              f"({fmt_dur(time.perf_counter() - t0)})")
    return found


def name_curies(curies):
    ids = [str(c) for c in curies if str(c)]
    if not ids:
        log.info("  name_curies called with no CURIEs; nothing to do")
        return []
    t0 = time.perf_counter()
    conn = _node_db()
    out = []
    n_chunks = (len(ids) + 499) // 500
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        q = f"SELECT id, name, category FROM nodes WHERE id IN ({','.join('?' * len(chunk))})"
        out.extend(conn.execute(q, chunk).fetchall())
    named = [{"id": r[0], "name": r[1] or "", "category": r[2] or ""} for r in out]

    resolved = {r["id"] for r in named}
    missing = [c for c in ids if c not in resolved]
    log.info(f"  named {len(named)}/{len(ids)} CURIE(s) over {n_chunks} sqlite chunk(s) "
             f"in {fmt_dur(time.perf_counter() - t0)}")
    if missing:
        log.warning(f"  !! {len(missing)} CURIE(s) had no row in the node DB: "
                    f"{preview(missing)}")
    return named
