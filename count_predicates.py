"""Count predicates in the RTX-KG2 edges file, and verify subject/object vs :START_ID/:END_ID.

ONE full scan of the 38 GB edges file (~2 min): we read only the 6 columns we need into an
in-memory table, then all the counts/lists come off that instantly.  Run:

    python3 count_predicates.py

Edge columns (headerless data file; 0-indexed):
  0  core_predicate     <- normalized biolink predicate (what I called "61")
  4  :END_ID
 13  :START_ID
 15  predicate:TYPE     <- RAW source predicate (rdfs:subPropertyOf, biolink:..., etc.)
 16  subject
 17  object
"""
import duckdb

EDGES = "rtx-kg2_edges_2.8.1.tsv"
READ_OPTS = ("delim='\t', header=false, quote='', escape='', ALL_VARCHAR=true, "
             "max_line_size=10000000, strict_mode=false, ignore_errors=true")

con = duckdb.connect()
con.execute("SET enable_progress_bar=true")

print(f"Scanning {EDGES} once (reading only the 6 needed columns)...\n")
con.execute(f"""
    CREATE TABLE e AS
    SELECT column00 AS core_predicate, column15 AS predicate_type,
           column16 AS subject, column13 AS start_id,
           column17 AS object,  column04 AS end_id
    FROM read_csv('{EDGES}', {READ_OPTS})
""")

total, n_core, n_ptype, subj_bad, obj_bad = con.execute("""
    SELECT count(*),
           count(DISTINCT core_predicate),
           count(DISTINCT predicate_type),
           count(*) FILTER (WHERE subject IS DISTINCT FROM start_id),
           count(*) FILTER (WHERE object  IS DISTINCT FROM end_id)
    FROM e
""").fetchone()

print("================ PREDICATE COUNTS ================")
print(f"total edges                       : {total:,}")
print(f"distinct core_predicate (col 0)   : {n_core:,}   <- normalized biolink ('the 61')")
print(f"distinct predicate:TYPE (col 15)  : {n_ptype:,}   <- raw source predicate")
print()
print("=========== subject/object vs START/END ==========")
print(f"rows where subject != :START_ID   : {subj_bad:,}")
print(f"rows where object  != :END_ID     : {obj_bad:,}")
print(f"=> subject == :START_ID for ALL rows? {subj_bad == 0}")
print(f"=> object  == :END_ID   for ALL rows? {obj_bad == 0}")

# full distinct lists (with counts) for inspection
for col in ["core_predicate", "predicate_type"]:
    con.execute(f"""COPY (SELECT {col} AS predicate, count(*) AS n
                          FROM e GROUP BY 1 ORDER BY n DESC)
                    TO 'distinct_{col}.tsv' (FORMAT csv, DELIMITER '\t', HEADER)""")
    print(f"\nwrote distinct_{col}.tsv")
