"""eCFR analyzer, H1: Python + SQLite.

Usage (from the repo root):
  python h1/ecfr.py ingest --date 2026-10-29 [--titles 1,40,41]
  python h1/ecfr.py serve --port 8301
"""

import argparse
import concurrent.futures as cf
import gzip
import hashlib
import json
import os
import re
import sqlite3
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

API = "https://www.ecfr.gov/api"
STORE = "data/h1/ecfr.sqlite"
CUTOFF = "2017-01-01"  # earlier version rows are the eCFR baseline load, not changes
WORD = re.compile(r"[^\W_]+")
RESTRICTION = re.compile(r"\b(shall|must|may not|required|prohibited)\b")
ANCESTORS = {"SUBTITLE": "subtitle", "CHAPTER": "chapter", "SUBCHAP": "subchapter"}
USC = re.compile(r"(\d+)\s*U\.\s*S\.\s*C\.?\s+(\d+[A-Za-z]*)")
PUBLAW = re.compile(r"Pub\.\s*L\.|Public Law")
EXECUTIVE = re.compile(r"E\.\s*O\.|Executive Order|Proclamation|Reorganization Plan")
TAGS = ("statute", "housekeeping", "executive", "other", "none")

SCHEMA = """
CREATE TABLE part (title INT, part TEXT, ord INT, subtitle TEXT, chapter TEXT, subchapter TEXT,
                   heading TEXT, words INT, restrictions INT, hash TEXT, authority TEXT,
                   PRIMARY KEY (title, part));
CREATE TABLE part_cite (title INT, part TEXT, cite TEXT, PRIMARY KEY (title, part, cite));
CREATE TABLE version (title INT, part TEXT, type TEXT, identifier TEXT, date TEXT,
                      substantive INT, removed INT, PRIMARY KEY (title, part, type, identifier, date));
CREATE INDEX version_part ON version (title, part);
CREATE TABLE agency (slug TEXT PRIMARY KEY, name TEXT, short_name TEXT, parent_slug TEXT,
                     refs TEXT, children TEXT, words INT, restrictions INT, density REAL,
                     parts INT, checksum TEXT, changed INT, last_changed TEXT, authority_words TEXT,
                     sections INT, stale_sections INT, stale_share REAL);
CREATE TABLE agency_part (slug TEXT, title INT, part TEXT, PRIMARY KEY (slug, title, part));
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""


# ---------- download (raw cache layout is shared with H2/H3, see CONTRACT.md) ----------


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


# ---------- parse ----------


def normalize(text):
    return " ".join(unicodedata.normalize("NFC", text).split())


def authority(text):
    """Tag what a part's authority note cites (see CONTRACT.md). Descriptive, not a legal conclusion."""
    cites = {f"{t} U.S.C. {s}" for t, s in USC.findall(text)}
    if not text:
        return "none", cites
    if cites - {"5 U.S.C. 301"} or PUBLAW.search(text):
        return "statute", cites
    if cites:
        return "housekeeping", cites  # only the general Housekeeping Statute
    return ("executive" if EXECUTIVE.search(text) else "other"), cites


def parse_parts(path, title, outside):
    """Stream one title's XML and yield (part row, cites) per PART. Adds words outside parts to outside[0]."""
    stack, ord_ = [], 0  # (TYPE, N) of every open element
    with gzip.open(path) as f:
        for event, el in ET.iterparse(f, events=("start", "end")):
            if event == "start":
                stack.append((el.get("TYPE"), el.get("N")))
                continue
            stack.pop()
            if el.get("TYPE") == "TITLE":  # parts are cleared by now, so only outside text remains
                outside[0] += len(WORD.findall(normalize(" ".join(el.itertext()))))
            if el.get("TYPE") != "PART":
                continue
            ancestors = {ANCESTORS[t]: n for t, n in stack if t in ANCESTORS}  # innermost wins
            text = normalize(" ".join(el.itertext()))
            head = el.find("HEAD")
            tag, cites = authority(
                " ".join(normalize(" ".join(a.itertext())) for a in el.iter("AUTH"))
            )
            yield (
                (
                    title,
                    el.get("N"),
                    ord_,
                    ancestors.get("subtitle"),
                    ancestors.get("chapter"),
                    ancestors.get("subchapter"),
                    normalize(" ".join(head.itertext())) if head is not None else "",
                    len(WORD.findall(text)),
                    len(RESTRICTION.findall(text.lower())),
                    hashlib.sha256(text.encode()).hexdigest(),
                    tag,
                ),
                cites,
            )
            ord_ += 1
            el.clear()  # collect first, then free: the text above is what we measure


def load_versions(db, title, path, date):
    with open(path) as f:
        rows = json.load(f)["content_versions"]
    db.executemany(
        """INSERT INTO version VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT DO UPDATE SET substantive = max(substantive, excluded.substantive),
                                     removed = max(removed, excluded.removed)""",
        [
            (
                title,
                r["part"] or "",  # chapter-level appendices have no part; "" never matches one
                r["type"],
                r["identifier"],
                r["date"],
                r["substantive"],
                r["removed"],
            )
            for r in rows
            if r["date"] <= date
        ],
    )


# ---------- agencies and metrics ----------

MATCH = """INSERT OR IGNORE INTO agency_part SELECT :slug, title, part FROM part
           WHERE title = :title AND (:subtitle IS NULL OR subtitle = :subtitle)
             AND (:chapter IS NULL OR chapter = :chapter)
             AND (:subchapter IS NULL OR subchapter = :subchapter) AND (:part IS NULL OR part = :part)"""


def load_agencies(db, agencies):
    for a in agencies:
        family = [(a, None)] + [(c, a["slug"]) for c in a["children"]]
        for agency, parent in family:
            db.execute(
                "INSERT INTO agency (slug, name, short_name, parent_slug, refs, children) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    agency["slug"],
                    agency["name"],
                    agency.get("short_name"),
                    parent,
                    json.dumps(agency["cfr_references"]),
                    json.dumps([c["slug"] for c in agency.get("children", [])]),
                ),
            )
        # A parent's set is its own refs plus every child's refs; INSERT OR IGNORE counts each part once.
        for agency, refs in [(a, [r for f, _ in family for r in f["cfr_references"]])] + [
            (c, c["cfr_references"]) for c in a["children"]
        ]:
            for ref in refs:
                keys = ("title", "subtitle", "chapter", "subchapter", "part")
                db.execute(MATCH, {"slug": agency["slug"], **{k: ref.get(k) for k in keys}})


def compute_metrics(db, previous):
    db.execute("""UPDATE agency SET
        words = (SELECT coalesce(sum(p.words), 0) FROM agency_part ap JOIN part p USING (title, part) WHERE ap.slug = agency.slug),
        restrictions = (SELECT coalesce(sum(p.restrictions), 0) FROM agency_part ap JOIN part p USING (title, part) WHERE ap.slug = agency.slug),
        parts = (SELECT count(*) FROM agency_part ap WHERE ap.slug = agency.slug),
        last_changed = (SELECT max(v.date) FROM agency_part ap JOIN version v USING (title, part) WHERE ap.slug = agency.slug)""")
    db.execute(
        "UPDATE agency SET density = CASE WHEN words > 0 THEN 1000.0 * restrictions / words END"
    )
    digests = {}
    rows = db.execute("""SELECT ap.slug, p.title, p.part, p.hash FROM agency_part ap
                         JOIN part p USING (title, part) ORDER BY ap.slug, p.title, p.ord""")
    for slug, title, part, digest in rows:
        digests.setdefault(slug, hashlib.sha256()).update(f"{title}|{part}|{digest}\n".encode())
    for slug, h in digests.items():
        checksum = h.hexdigest()
        changed = previous.get(slug) is not None and previous[slug] != checksum
        db.execute(
            "UPDATE agency SET checksum = ?, changed = ? WHERE slug = ?", (checksum, changed, slug)
        )
    db.execute("UPDATE agency SET changed = 0 WHERE changed IS NULL")
    by_tag = ", ".join(
        f"'{t}', coalesce(sum(p.words) FILTER (WHERE p.authority = '{t}'), 0)" for t in TAGS
    )
    db.execute(f"""UPDATE agency SET
        authority_words = (SELECT json_object({by_tag}) FROM agency_part ap JOIN part p USING (title, part)
                           WHERE ap.slug = agency.slug),
        sections = (SELECT count(*) FROM agency_part ap JOIN section s USING (title, part) WHERE ap.slug = agency.slug),
        stale_sections = (SELECT coalesce(sum(s.stale), 0) FROM agency_part ap JOIN section s USING (title, part)
                          WHERE ap.slug = agency.slug)""")
    db.execute(
        "UPDATE agency SET stale_share = CASE WHEN sections > 0 THEN 1.0 * stale_sections / sections END"
    )
    return by_tag


def build_sections(db):
    """One row per current section (latest version not removed, part still exists); stale = no change since 2017."""
    db.execute(f"""CREATE TABLE section AS SELECT title, part, date < '{CUTOFF}' AS stale FROM (
        SELECT title, part, date, removed, row_number() OVER (
            PARTITION BY title, part, type, identifier ORDER BY date DESC) AS n FROM version)
        WHERE n = 1 AND NOT removed AND (title, part) IN (SELECT title, part FROM part)""")


def ingest(date, titles):
    raw, titles = download(date, titles)
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    previous = {}
    if os.path.exists(STORE):
        with sqlite3.connect(STORE) as old:
            previous = dict(old.execute("SELECT slug, checksum FROM agency"))
    tmp = STORE + ".new"
    if os.path.exists(tmp):
        os.remove(tmp)
    db = sqlite3.connect(tmp)
    db.executescript(SCHEMA)
    outside = [0]
    for n in titles:
        for row, cites in parse_parts(f"{raw}/title-{n}.xml.gz", n, outside):
            db.execute("INSERT INTO part VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", row)
            db.executemany(
                "INSERT INTO part_cite VALUES (?, ?, ?)", [(n, row[1], c) for c in cites]
            )
        load_versions(db, n, f"{raw}/versions-{n}.json", date)
    with open(f"{raw}/agencies.json") as f:
        load_agencies(db, json.load(f)["agencies"])
    build_sections(db)
    by_tag = compute_metrics(db, previous)
    q = lambda sql: db.execute(sql).fetchone()[0]  # noqa: E731
    meta = {
        "ecfr_date": date,
        "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "titles": titles,
        "parts": q("SELECT count(*) FROM part"),
        "words": q("SELECT coalesce(sum(words), 0) FROM part"),
        "unattributed_words": q(
            "SELECT coalesce(sum(words), 0) FROM part p WHERE NOT EXISTS "
            "(SELECT 1 FROM agency_part ap WHERE ap.title = p.title AND ap.part = p.part)"
        ),
        "baseline_rows": q(f"SELECT count(*) FROM version WHERE date < '{CUTOFF}'"),
        "change_rows": q(f"SELECT count(*) FROM version WHERE date >= '{CUTOFF}'"),
        "unmatched_events": q(
            f"SELECT count(*) FROM version v WHERE date >= '{CUTOFF}' AND NOT EXISTS "
            "(SELECT 1 FROM part p WHERE p.title = v.title AND p.part = v.part)"
        ),
        "sections": q("SELECT count(*) FROM section"),
        "stale_sections": q("SELECT coalesce(sum(stale), 0) FROM section"),
        "authority_words": json.loads(q(f"SELECT json_object({by_tag}) FROM part p")),
    }
    db.execute("INSERT INTO meta VALUES ('meta', ?)", (json.dumps(meta),))
    db.commit()
    report(db, titles, meta, outside[0])
    db.close()
    os.replace(tmp, STORE)


def report(db, titles, meta, outside_words):
    print(
        f"{meta['parts']} parts, {meta['words']} words in parts, {outside_words} words outside parts"
    )
    for title, share, latest in db.execute(f"""SELECT title, avg(date < '{CUTOFF}'),
            max(CASE WHEN date < '{CUTOFF}' THEN date END) FROM version GROUP BY title"""):
        print(
            f"title {title}: {share:.0%} of version rows are baseline (latest baseline date {latest})"
        )
    for slug, refs in db.execute("SELECT slug, refs FROM agency WHERE parts = 0"):
        if any(r["title"] in titles for r in json.loads(refs)):
            print(f"warning: {slug} has refs in ingested titles but matched no parts")


# ---------- API ----------

FIELDS = (
    "slug",
    "name",
    "short_name",
    "parent_slug",
    "words",
    "restrictions",
    "density",
    "parts",
    "checksum",
    "changed",
    "last_changed",
    "authority_words",
    "sections",
    "stale_sections",
    "stale_share",
)


def serve(port):
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse

    app = FastAPI(title="eCFR analyzer (H1: Python + SQLite)")

    def query(sql, *args):
        # One read-only connection per request: sqlite3 connections must not cross FastAPI's threads.
        with sqlite3.connect(f"file:{STORE}?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            return db.execute(sql, args).fetchall()

    def agency_json(row):
        convert = {"changed": bool, "authority_words": json.loads}
        return {k: convert.get(k, lambda v: v)(row[k]) for k in FIELDS}

    def one_agency(slug):
        rows = query("SELECT * FROM agency WHERE slug = ?", slug)
        if not rows:
            raise HTTPException(404, "not found")
        return rows[0]

    @app.get("/")
    def index():
        return FileResponse("web/index.html")

    @app.get("/api/meta")
    def meta():
        return json.loads(query("SELECT value FROM meta WHERE key = 'meta'")[0][0])

    @app.get("/api/agencies")
    def agencies():
        return [agency_json(r) for r in query("SELECT * FROM agency ORDER BY words DESC, slug")]

    @app.get("/api/agencies/{slug}")
    def agency(slug: str):
        row = one_agency(slug)
        top = query(
            """SELECT p.title, p.part, p.heading, p.words, p.restrictions, p.authority FROM agency_part ap
                       JOIN part p USING (title, part) WHERE ap.slug = ?
                       ORDER BY p.words DESC, p.title, p.ord LIMIT 10""",
            slug,
        )
        statutes = query(
            """SELECT c.cite, count(*) AS parts, sum(p.words) AS words FROM agency_part ap
               JOIN part_cite c USING (title, part) JOIN part p USING (title, part)
               WHERE ap.slug = ? GROUP BY c.cite ORDER BY words DESC, c.cite LIMIT 10""",
            slug,
        )
        return {
            **agency_json(row),
            "refs": json.loads(row["refs"]),
            "children": json.loads(row["children"]),
            "top_parts": [dict(r) for r in top],
            "top_statutes": [dict(r) for r in statutes],
        }

    @app.get("/api/agencies/{slug}/history")
    def history(slug: str):
        one_agency(slug)
        years = query(
            f"""SELECT CAST(substr(v.date, 1, 4) AS INT) AS year,
                              sum(NOT v.removed AND v.substantive) AS substantive,
                              sum(NOT v.removed AND NOT v.substantive) AS nonsubstantive,
                              sum(v.removed) AS removed
                          FROM agency_part ap JOIN version v USING (title, part)
                          WHERE ap.slug = ? AND v.date >= '{CUTOFF}' GROUP BY year ORDER BY year""",
            slug,
        )
        return {"slug": slug, "years": [dict(r) for r in years]}

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = cli.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest")
    ing.add_argument("--date", required=True)
    ing.add_argument("--titles", type=lambda s: [int(t) for t in s.split(",")], default=[])
    sub.add_parser("serve").add_argument("--port", type=int, default=8301)
    args = cli.parse_args()
    ingest(args.date, args.titles) if args.cmd == "ingest" else serve(args.port)
