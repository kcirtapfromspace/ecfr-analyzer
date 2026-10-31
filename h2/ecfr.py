"""eCFR analyzer, H2: Python parses, DuckDB computes, Parquet stores.

Usage (from the repo root):
  python h2/ecfr.py ingest --date 2026-10-29 [--titles 1,40,41]
  python h2/ecfr.py serve --port 8302
"""

import argparse
import concurrent.futures as cf
import gzip
import hashlib
import itertools
import json
import os
import re
import shutil
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import duckdb

API = "https://www.ecfr.gov/api"
STORE = "data/h2"
CUTOFF = "2017-01-01"  # earlier version rows are the eCFR baseline load, not changes
ANCESTORS = {"SUBTITLE": "subtitle", "CHAPTER": "chapter", "SUBCHAP": "subchapter"}
# Per-part counts happen while parsing: DuckDB's regexp_extract_all over 109M words peaked above 2 GB.
WORD = re.compile(r"[^\W_]+")
RESTRICTION = re.compile(r"\b(shall|must|may not|required|prohibited)\b")
USC = re.compile(r"(\d+)\s*U\.\s*S\.\s*C\.?\s+(\d+[A-Za-z]*)")
PUBLAW = re.compile(r"Pub\.\s*L\.|Public Law")
EXECUTIVE = re.compile(r"E\.\s*O\.|Executive Order|Proclamation|Reorganization Plan")
TAGS = ("statute", "housekeeping", "executive", "other", "none")


# ---------- download (raw cache layout is shared with H1/H3, see CONTRACT.md) ----------


def fetch(url, gzip_body=False):
    headers = {"Accept-Encoding": "gzip"} if gzip_body else {}
    for attempt in range(6):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=300
            ) as r:
                return r.read()  # urllib does not decode gzip, so the body is stored as sent
        except OSError:  # includes HTTP 429: eCFR rate-limits bursts and sends no Retry-After
            if attempt == 5:
                raise
            time.sleep(min(60, 5 * 2**attempt))


def cached(path, make):
    """Create path from make() unless it already exists; write-then-rename so partial files never count."""
    if not os.path.exists(path):
        with open(path + ".tmp", "wb") as f:
            f.write(make())
        os.replace(path + ".tmp", path)
    return path


def fetch_versions(title):
    url = f"{API}/versioner/v1/versions/title-{title}.json?page="
    first = json.loads(fetch(url + "1"))
    rows = first["content_versions"]
    for page in range(2, int(first["meta"]["total_pages"]) + 1):
        rows += json.loads(fetch(url + str(page)))["content_versions"]
    expected = int(first["meta"]["result_count"])
    if len(rows) != expected:
        raise SystemExit(f"title {title}: fetched {len(rows)} version rows, expected {expected}")
    return json.dumps({"result_count": expected, "content_versions": rows}).encode()


def download(date, titles):
    raw = f"data/raw/{date}"
    os.makedirs(raw, exist_ok=True)
    cached(f"{raw}/agencies.json", lambda: fetch(f"{API}/admin/v1/agencies.json"))
    with open(cached(f"{raw}/titles.json", lambda: fetch(f"{API}/versioner/v1/titles.json"))) as f:
        catalog = json.load(f)
    if catalog["meta"]["import_in_progress"]:
        raise SystemExit("eCFR reports an import in progress; try again later")
    titles = titles or [t["number"] for t in catalog["titles"] if not t["reserved"]]

    def one(n):
        cached(
            f"{raw}/title-{n}.xml.gz",
            lambda: fetch(f"{API}/versioner/v1/full/{date}/title-{n}.xml", True),
        )
        cached(f"{raw}/versions-{n}.json", lambda: fetch_versions(n))

    with cf.ThreadPoolExecutor(2) as pool:
        list(pool.map(one, titles))
    return raw, sorted(titles)


# ---------- parse: Python only extracts structure and normalized text ----------


def normalize(text):
    return " ".join(unicodedata.normalize("NFC", text).split())


def authority(text):
    """Tag what a part's authority note cites (see CONTRACT.md). Descriptive, not a legal conclusion."""
    cites = sorted({f"{t} U.S.C. {s}" for t, s in USC.findall(text)})
    if not text:
        return "none", cites
    if set(cites) - {"5 U.S.C. 301"} or PUBLAW.search(text):
        return "statute", cites
    if cites:
        return "housekeeping", cites  # only the general Housekeeping Statute
    return ("executive" if EXECUTIVE.search(text) else "other"), cites


def parse_parts(path, title):
    """Stream one title's XML and yield a row per PART, including its normalized text."""
    stack, ord_ = [], 0  # (TYPE, N) of every open element
    with gzip.open(path) as f:
        for event, el in ET.iterparse(f, events=("start", "end")):
            if event == "start":
                stack.append((el.get("TYPE"), el.get("N")))
                continue
            stack.pop()
            if el.get("TYPE") != "PART":
                continue
            ancestors = {ANCESTORS[t]: n for t, n in stack if t in ANCESTORS}  # innermost wins
            head = el.find("HEAD")
            text = normalize(" ".join(el.itertext()))
            tag, cites = authority(
                " ".join(normalize(" ".join(a.itertext())) for a in el.iter("AUTH"))
            )
            yield (
                title,
                el.get("N"),
                ord_,
                ancestors.get("subtitle"),
                ancestors.get("chapter"),
                ancestors.get("subchapter"),
                normalize(" ".join(head.itertext())) if head is not None else "",
                text,
                len(WORD.findall(text)),
                len(RESTRICTION.findall(text.lower())),
                hashlib.sha256(text.encode()).hexdigest(),
                tag,
                cites,
            )
            ord_ += 1
            el.clear()  # collect first, then free


def load_agencies(db, agencies):
    keys = ("title", "subtitle", "chapter", "subchapter", "part")
    for a in agencies:
        family = [(a, None)] + [(c, a["slug"]) for c in a["children"]]
        for agency, parent in family:
            db.execute(
                "INSERT INTO agency VALUES (?, ?, ?, ?, ?, ?)",
                (
                    agency["slug"],
                    agency["name"],
                    agency.get("short_name"),
                    parent,
                    json.dumps(agency["cfr_references"]),
                    json.dumps([c["slug"] for c in agency.get("children", [])]),
                ),
            )
            # Each agency owns its refs; a parent also owns every child's refs (DISTINCT below dedupes parts).
            owners = [agency["slug"]] + ([parent] if parent else [])
            refs = [
                (o, *(r.get(k) for k in keys)) for o in owners for r in agency["cfr_references"]
            ]
            if refs:  # some child agencies have no refs, and DuckDB rejects an empty executemany
                db.executemany("INSERT INTO ref VALUES (?, ?, ?, ?, ?, ?)", refs)


# ---------- analytics: all metrics are DuckDB SQL ----------

ANALYTICS = r"""
CREATE TABLE version AS
  SELECT title, part, type, identifier, date, bool_or(substantive) AS substantive,
         bool_or(removed) AS removed
  FROM version_row WHERE date <= '{date}' GROUP BY ALL;

CREATE TABLE agency_part AS
  SELECT DISTINCT r.slug, p.title, p.part FROM ref r JOIN part p ON p.title = r.title
    AND (r.subtitle IS NULL OR p.subtitle = r.subtitle) AND (r.chapter IS NULL OR p.chapter = r.chapter)
    AND (r.subchapter IS NULL OR p.subchapter = r.subchapter) AND (r.part IS NULL OR p.part = r.part);

CREATE TABLE section AS
  SELECT title, part, date < '{cutoff}' AS stale FROM (
    SELECT *, row_number() OVER (PARTITION BY title, part, type, identifier ORDER BY date DESC) AS n
    FROM version) v
  WHERE n = 1 AND NOT removed AND EXISTS (SELECT 1 FROM part p WHERE p.title = v.title AND p.part = v.part);

CREATE TABLE agency_metric AS
  SELECT a.*, coalesce(m.words, 0) AS words, coalesce(m.restrictions, 0) AS restrictions,
         CASE WHEN m.words > 0 THEN CAST(1000 AS DOUBLE) * m.restrictions / m.words END AS density,
         coalesce(m.parts, 0) AS parts, m.checksum,
         coalesce(old.checksum IS NOT NULL AND old.checksum <> m.checksum, false) AS changed,
         h.last_changed, coalesce(m.authority_words, '{zero}') AS authority_words,
         coalesce(st.sections, 0) AS sections, coalesce(st.stale_sections, 0) AS stale_sections,
         CASE WHEN st.sections > 0 THEN CAST(st.stale_sections AS DOUBLE) / st.sections END AS stale_share
  FROM agency a
  LEFT JOIN (SELECT ap.slug, CAST(sum(p.words) AS BIGINT) AS words, CAST(sum(p.restrictions) AS BIGINT) AS restrictions,
                    count(*) AS parts,
                    sha256(string_agg(p.title || '|' || p.part || '|' || p.hash || chr(10), '' ORDER BY p.title, p.ord))
                      AS checksum,
                    CAST(json_object({by_tag}) AS VARCHAR) AS authority_words
             FROM agency_part ap JOIN part p USING (title, part) GROUP BY ap.slug) m USING (slug)
  LEFT JOIN (SELECT ap.slug, count(*) AS sections, CAST(sum(CAST(s.stale AS INT)) AS BIGINT) AS stale_sections
             FROM agency_part ap JOIN section s USING (title, part) GROUP BY ap.slug) st USING (slug)
  LEFT JOIN (SELECT ap.slug, max(v.date) AS last_changed FROM agency_part ap JOIN version v USING (title, part)
             GROUP BY ap.slug) h USING (slug)
  LEFT JOIN previous old USING (slug);
"""


def ingest(date, titles):
    raw, titles = download(date, titles)
    # Build the new store next to the old one, then swap directories, so a failed ingest keeps the old data.
    # The build database is a file with a memory cap, so DuckDB spills to disk instead of holding all text in RAM.
    new = STORE + ".new"
    shutil.rmtree(new, ignore_errors=True)
    os.makedirs(new)
    db = duckdb.connect(f"{new}/build.duckdb")
    db.execute("SET memory_limit = '1GB'")
    db.execute("""CREATE TABLE part (title INT, part VARCHAR, ord INT, subtitle VARCHAR, chapter VARCHAR,
                  subchapter VARCHAR, heading VARCHAR, text VARCHAR, words INT, restrictions INT,
                  hash VARCHAR, authority VARCHAR, cites VARCHAR[])""")
    db.execute(
        "CREATE TABLE agency (slug VARCHAR, name VARCHAR, short_name VARCHAR, parent_slug VARCHAR, "
        "refs VARCHAR, children VARCHAR)"
    )
    db.execute(
        "CREATE TABLE ref (slug VARCHAR, title INT, subtitle VARCHAR, chapter VARCHAR, "
        "subchapter VARCHAR, part VARCHAR)"
    )
    db.execute(
        "CREATE TABLE version_row (title INT, part VARCHAR, type VARCHAR, identifier VARCHAR, "
        "date VARCHAR, substantive BOOLEAN, removed BOOLEAN)"
    )
    for n in titles:
        # One file per statement: reading all versions files at once needed > 1 GB of JSON buffers.
        db.execute(f"""INSERT INTO version_row SELECT {n}, v.part, v.type, v.identifier,
                         CAST(v.date AS VARCHAR), v.substantive, v.removed
                       FROM (SELECT unnest(content_versions) AS v
                             FROM read_json('{raw}/versions-{n}.json', maximum_object_size = 64000000))""")
        for batch in itertools.batched(parse_parts(f"{raw}/title-{n}.xml.gz", n), 100):
            db.executemany(
                "INSERT INTO part VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", list(batch)
            )
    with open(f"{raw}/agencies.json") as f:
        load_agencies(db, json.load(f)["agencies"])
    old = f"{STORE}/agencies.parquet"
    db.execute(
        f"CREATE TABLE previous AS SELECT slug, checksum FROM '{old}'"
        if os.path.exists(old)
        else "CREATE TABLE previous (slug VARCHAR, checksum VARCHAR)"
    )
    by_tag = ", ".join(
        f"'{t}', coalesce(sum(p.words) FILTER (WHERE p.authority = '{t}'), 0)" for t in TAGS
    )
    zero = json.dumps(dict.fromkeys(TAGS, 0))
    sql = ANALYTICS.format(date=date, cutoff=CUTOFF, by_tag=by_tag, zero=zero)
    for statement in sql.split(";"):
        if statement.strip():
            db.execute(statement)
    dupes = db.sql("SELECT count(*) - count(DISTINCT (title, part)) FROM part").fetchone()[0]
    if dupes:
        raise SystemExit(f"{dupes} duplicate (title, part) keys")
    q = lambda sql: db.sql(sql).fetchone()[0]  # noqa: E731
    meta = {
        "ecfr_date": date,
        "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "titles": titles,
        "parts": q("SELECT count(*) FROM part"),
        "words": int(q("SELECT coalesce(sum(words), 0) FROM part")),
        "unattributed_words": int(
            q("SELECT coalesce(sum(words), 0) FROM part ANTI JOIN agency_part USING (title, part)")
        ),
        "baseline_rows": q(f"SELECT count(*) FROM version WHERE date < '{CUTOFF}'"),
        "change_rows": q(f"SELECT count(*) FROM version WHERE date >= '{CUTOFF}'"),
        "unmatched_events": q(
            f"SELECT count(*) FROM version v WHERE date >= '{CUTOFF}' "
            "AND NOT EXISTS (SELECT 1 FROM part p WHERE p.title = v.title AND p.part = v.part)"
        ),
        "sections": q("SELECT count(*) FROM section"),
        "stale_sections": int(q("SELECT coalesce(sum(CAST(stale AS INT)), 0) FROM section")),
        "authority_words": json.loads(
            q(f"SELECT CAST(json_object({by_tag}) AS VARCHAR) FROM part p")
        ),
    }
    for table, name in [
        ("part", "parts"),
        ("version", "versions"),
        ("agency_part", "agency_parts"),
        ("agency_metric", "agencies"),
    ]:
        db.execute(
            f"COPY {table} TO '{new}/{name}.parquet' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 1000)"
        )
    with open(f"{new}/meta.json", "w") as f:
        json.dump(meta, f)
    report(db, titles, meta)
    db.close()
    os.remove(f"{new}/build.duckdb")
    if os.path.exists(STORE):
        os.replace(STORE, STORE + ".old")
    os.replace(new, STORE)
    shutil.rmtree(STORE + ".old", ignore_errors=True)


def report(db, titles, meta):
    print(f"{meta['parts']} parts, {meta['words']} words in parts")
    for title, share, latest in db.sql(f"""SELECT title, avg(CAST(date < '{CUTOFF}' AS INT)),
            max(CASE WHEN date < '{CUTOFF}' THEN date END) FROM version GROUP BY title ORDER BY title""").fetchall():
        print(
            f"title {title}: {share:.0%} of version rows are baseline (latest baseline date {latest})"
        )
    for slug, refs in db.sql("SELECT slug, refs FROM agency_metric WHERE parts = 0").fetchall():
        if any(r["title"] in titles for r in json.loads(refs)):
            print(f"warning: {slug} has refs in ingested titles but matched no parts")


# ---------- API ----------

FIELDS = (
    "slug, name, short_name, parent_slug, words, restrictions, density, parts, checksum, changed, "
    "last_changed, authority_words, sections, stale_sections, stale_share"
)


def serve(port):
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse

    app = FastAPI(title="eCFR analyzer (H2: DuckDB + Parquet)")
    con = duckdb.connect()
    for name in ("parts", "versions", "agency_parts", "agencies"):
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM '{STORE}/{name}.parquet'")
    with open(f"{STORE}/meta.json") as f:
        meta_json = json.load(f)

    def query(sql, *args):
        cur = (
            con.cursor()
        )  # a DuckDB connection is not thread-safe; each request gets its own cursor
        cur.execute(sql, list(args))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def agency_json(row):
        return {**row, "authority_words": json.loads(row["authority_words"])}

    def one_agency(slug):
        rows = query("SELECT * FROM agencies WHERE slug = ?", slug)
        if not rows:
            raise HTTPException(404, "not found")
        return rows[0]

    @app.get("/")
    def index():
        return FileResponse("web/index.html")

    @app.get("/api/meta")
    def meta():
        return meta_json

    @app.get("/api/agencies")
    def agencies():
        return [
            agency_json(r)
            for r in query(f"SELECT {FIELDS} FROM agencies ORDER BY words DESC, slug")
        ]

    @app.get("/api/agencies/{slug}")
    def agency(slug: str):
        row = one_agency(slug)
        top = query(
            """SELECT p.title, p.part, p.heading, p.words, p.restrictions, p.authority FROM agency_parts ap
                       JOIN parts p USING (title, part) WHERE ap.slug = ?
                       ORDER BY p.words DESC, p.title, p.ord LIMIT 10""",
            slug,
        )
        statutes = query(
            """SELECT c.cite, count(*) AS parts, CAST(sum(c.words) AS BIGINT) AS words FROM agency_parts ap
               JOIN (SELECT title, part, words, unnest(cites) AS cite FROM parts) c USING (title, part)
               WHERE ap.slug = ? GROUP BY c.cite ORDER BY words DESC, c.cite LIMIT 10""",
            slug,
        )
        summary = {k: row[k] for k in FIELDS.replace(",", " ").split()}
        return {
            **agency_json(summary),
            "refs": json.loads(row["refs"]),
            "children": json.loads(row["children"]),
            "top_parts": top,
            "top_statutes": statutes,
        }

    @app.get("/api/agencies/{slug}/history")
    def history(slug: str):
        one_agency(slug)
        years = query(
            f"""SELECT CAST(substr(v.date, 1, 4) AS INT) AS year,
                              count(*) FILTER (WHERE NOT v.removed AND v.substantive) AS substantive,
                              count(*) FILTER (WHERE NOT v.removed AND NOT v.substantive) AS nonsubstantive,
                              count(*) FILTER (WHERE v.removed) AS removed
                          FROM agency_parts ap JOIN versions v USING (title, part)
                          WHERE ap.slug = ? AND v.date >= '{CUTOFF}' GROUP BY year ORDER BY year""",
            slug,
        )
        return {"slug": slug, "years": years}

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = cli.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest")
    ing.add_argument("--date", required=True)
    ing.add_argument("--titles", type=lambda s: [int(t) for t in s.split(",")], default=[])
    sub.add_parser("serve").add_argument("--port", type=int, default=8302)
    args = cli.parse_args()
    ingest(args.date, args.titles) if args.cmd == "ingest" else serve(args.port)
