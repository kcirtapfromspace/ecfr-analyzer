"""eCFR analyzer: daily incremental ingest into Parquet, a static site export, and a JSON API.

Usage (from the repo root; the store defaults to --store data/app):
  uv run app/ecfr.py ingest [--date D] [--titles 1,40] [--full]   incremental against the store unless --full
  uv run app/ecfr.py export [--out site]                          static site: pages, JSON API, Parquet
  uv run app/ecfr.py serve [--port 8310] [--site site]            JSON API (+ /docs) serving the exported site
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
STORE = "data/app"  # set by --store
METRICS_VERSION = "r3"  # bump when per-part metrics change: stored metrics are then recomputed
CUTOFF = "2017-01-01"  # earlier version rows are the eCFR baseline load, not changes
ANCESTORS = {"SUBTITLE": "subtitle", "CHAPTER": "chapter", "SUBCHAP": "subchapter"}
WORD = re.compile(r"[^\W_]+")
RESTRICTION = re.compile(r"\b(shall|must|may not|required|prohibited)\b")
USC = re.compile(r"(\d+)\s*U\.\s*S\.\s*C\.?\s+(\d+[A-Za-z]*)")
PUBLAW = re.compile(r"Pub\.\s*L\.|Public Law")
EXECUTIVE = re.compile(r"E\.\s*O\.|Executive Order|Proclamation|Reorganization Plan")
TAGS = ("statute", "housekeeping", "executive", "other", "none")

# Sentence structure (CONTRACT.md, Round 3). Approximate by design: legal text defeats simple splitters.
BOUNDARY = re.compile(r'(?<=[.?!])\s+(?=[A-Z(§"“])')
ABBREVIATION = re.compile(
    r"(?:^|[\s(])(?:U\.S\.C|U\.S|e\.g|i\.e|etc|et seq|No|Nos|Sec|Secs|Pub|L|Stat|Fed|Reg|Inc|Co|Corp"
    r"|Ltd|Dr|Mr|Mrs|Ms|St|Jr|Vol|Ch|Pt|App|cf|al|approx|ft|in|lb|lbs|oz|Jan|Feb|Mar|Apr|Jun|Jul"
    r"|Aug|Sep|Sept|Oct|Nov|Dec|[A-Z])\.$"
)
VOWELS = re.compile(r"[aeiouy]+")
NO_VOWEL_WORD = re.compile(r"(?<![^\W_])[^\W_aeiouy]+(?![^\W_])")  # whole words with no vowel run
PASSIVE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?\w+(?:ed|en)\b")
CROSSREF = re.compile(
    r"§|\bparagraphs? \(|\bsections? \d|\bparts? \d|\bsubparts? [a-z]\b|u\.s\.c\."
)
DEFINITION = re.compile(
    r"\b(?:means|is defined as|has the meaning|have the meaning|as used in this)\b"
)
PROHIBITION = re.compile(
    r"\b(?:shall not|must not|may not|is prohibited|are prohibited|prohibited from"
    r"|no person shall|no person may)\b"
)
DUTY = re.compile(r"\b(?:shall|must|is required to|are required to)\b")
FILING = re.compile(
    r"\b(?:report|reports|record|records|recordkeeping|submit|submits|submitted|notify|notification"
    r"|certify|certification|application|apply|file|filing|disclose|disclosure|form|forms)\b"
)
OBLIGATION = re.compile(r"\b(?:shall|must|is required to|are required to|required)\b")
PERMISSION = re.compile(r"\bmay\b")
TYPES = ("definition", "prohibition", "paperwork", "obligation", "permission", "other")
INPUTS = ("size", "density", "grade", "directive", "paperwork", "staleness")


# ---------- download (raw cache layout is shared with H1/H2/H3, see CONTRACT.md) ----------


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


def stamps(doc):
    """Per-title (latest amended, latest issued) dates: a title whose pair moved has new content."""
    return {
        t["number"]: (t["latest_amended_on"], t["latest_issue_date"])
        for t in doc["titles"]
        if not t["reserved"]
    }


def catalog(date):
    """titles.json, the daily change signal: cached per snapshot date, otherwise fetched fresh."""
    if date and (doc := load_json(f"data/raw/{date}/titles.json")):
        return date, doc
    doc = json.loads(fetch(f"{API}/versioner/v1/titles.json"))
    date = date or doc["meta"]["date"]
    os.makedirs(f"data/raw/{date}", exist_ok=True)
    cached(f"data/raw/{date}/titles.json", lambda: json.dumps(doc).encode())
    return date, doc


def fetch_versions(title, since=None):
    """All version rows of a title, or only those issued on/after `since` (the daily delta)."""
    url = f"{API}/versioner/v1/versions/title-{title}.json?"
    url += f"issue_date%5Bgte%5D={since}&page=" if since else "page="
    first = json.loads(fetch(url + "1"))
    rows = first["content_versions"]
    for page in range(2, int(first["meta"]["total_pages"]) + 1):
        rows += json.loads(fetch(url + str(page)))["content_versions"]
    expected = int(first["meta"]["result_count"])
    if len(rows) != expected:
        raise SystemExit(f"title {title}: fetched {len(rows)} version rows, expected {expected}")
    return json.dumps({"result_count": expected, "content_versions": rows}).encode()


def download(date, since):
    """Fetch agencies, then XML and versions for each title in `since` ({title: None or delta start date})."""
    raw = f"data/raw/{date}"
    cached(f"{raw}/agencies.json", lambda: fetch(f"{API}/admin/v1/agencies.json"))

    def one(n):
        cached(
            f"{raw}/title-{n}.xml.gz",
            lambda: fetch(f"{API}/versioner/v1/full/{date}/title-{n}.xml", True),
        )
        suffix = f"-since-{since[n]}" if since[n] else ""
        return cached(f"{raw}/versions-{n}{suffix}.json", lambda: fetch_versions(n, since[n]))

    with cf.ThreadPoolExecutor(2) as pool:
        return raw, dict(zip(since, pool.map(one, since), strict=True))


# ---------- parse: Python extracts structure, text and per-part counts ----------


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


def prose(el):
    """Text pieces of el in document order, skipping tables and equations (their tail text is kept)."""
    if el.tag in ("TABLE", "MATH"):
        return
    if el.text:
        yield el.text
    for child in el:
        yield from prose(child)
        if child.tail:
            yield child.tail


def sentences(text):
    kept = []
    for piece in BOUNDARY.split(text):
        if kept and ABBREVIATION.search(kept[-1]):
            kept[-1] += " " + piece  # "U.S.C. 301" or "e.g. Part" is not a sentence break
        else:
            kept.append(piece)
    return [s for s in kept if WORD.search(s)]


def classify(sentence):
    """Typed decision per sentence; the first matching rule wins (CONTRACT.md)."""
    s = sentence.lower()
    if DEFINITION.search(s):
        return "definition"
    if PROHIBITION.search(s):
        return "prohibition"
    if DUTY.search(s) and FILING.search(s):
        return "paperwork"
    if OBLIGATION.search(s):
        return "obligation"
    return "permission" if PERMISSION.search(s) else "other"


def readability(text):
    """(prose_words, sentences, long_sentences, syllables, passive_sentences, crossrefs, *TYPES counts)."""
    lower = text.lower()
    found = sentences(text)
    types = dict.fromkeys(TYPES, 0)
    long_sentences = passive = 0
    for s in found:
        types[classify(s)] += 1
        long_sentences += len(WORD.findall(s)) > 40
        passive += bool(PASSIVE.search(s.lower()))
    # Σ max(1, vowel runs) per word = all vowel runs + one for each word that has none.
    syllables = len(VOWELS.findall(lower)) + len(NO_VOWEL_WORD.findall(lower))
    counts = (len(WORD.findall(text)), len(found), long_sentences, syllables, passive)
    return (*counts, len(CROSSREF.findall(lower)), *types.values())


def parse_parts(path, title, known):
    """Stream one title's XML and yield (part row, text) per PART. Sentence metrics, the slow step, are
    reused from `known` ({(part, prose hash): counts}) when a part's prose is unchanged."""
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
            auth = " ".join(normalize(" ".join(a.itertext())) for a in el.iter("AUTH"))
            tag, cites = authority(auth)
            prose_text = normalize(" ".join(prose(el)))
            prose_hash = hashlib.sha256(prose_text.encode()).hexdigest()
            row = (
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
                cites,
                prose_hash,
                *(known.get((el.get("N"), prose_hash)) or readability(prose_text)),
            )
            yield row, text
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


# ---------- analytics: everything after per-part counting is DuckDB SQL ----------

SUMMED = (
    "prose_words",
    "sentences",
    "long_sentences",
    "syllables",
    "passive_sentences",
    "crossrefs",
)
SUMMED += TYPES
PART_COLUMNS = (
    "title INT, part VARCHAR, ord INT, subtitle VARCHAR, chapter VARCHAR, subchapter VARCHAR, "
    "heading VARCHAR, words INT, restrictions INT, hash VARCHAR, authority VARCHAR, cites VARCHAR[], "
    "prose_hash VARCHAR, " + ", ".join(f"{c} INT" for c in SUMMED)
)
NAMES = ", ".join(column.split()[0] for column in PART_COLUMNS.split(", "))
SCHEMA = f"""
CREATE TABLE part ({PART_COLUMNS});
CREATE TABLE part_text (title INT, part VARCHAR, text VARCHAR);
CREATE TABLE agency (slug VARCHAR, name VARCHAR, short_name VARCHAR, parent_slug VARCHAR, refs VARCHAR,
                     children VARCHAR);
CREATE TABLE ref (slug VARCHAR, title INT, subtitle VARCHAR, chapter VARCHAR, subchapter VARCHAR, part VARCHAR);
CREATE TABLE version_row (title INT, part VARCHAR, type VARCHAR, identifier VARCHAR, date VARCHAR,
                          substantive BOOLEAN, removed BOOLEAN);
CREATE TABLE prev_part (title INT, part VARCHAR, heading VARCHAR, words INT, hash VARCHAR);
"""

ANALYTICS = r"""
CREATE TABLE version_all AS
  SELECT title, part, type, identifier, date, bool_or(substantive) AS substantive,
         bool_or(removed) AS removed
  FROM version_row GROUP BY ALL;

CREATE TABLE version AS SELECT * FROM version_all WHERE date <= '{date}';

CREATE TABLE agency_part AS
  SELECT DISTINCT r.slug, p.title, p.part FROM ref r JOIN part p ON p.title = r.title
    AND (r.subtitle IS NULL OR p.subtitle = r.subtitle) AND (r.chapter IS NULL OR p.chapter = r.chapter)
    AND (r.subchapter IS NULL OR p.subchapter = r.subchapter) AND (r.part IS NULL OR p.part = r.part);

CREATE TABLE section AS
  SELECT title, part, date < '{cutoff}' AS stale FROM (
    SELECT *, row_number() OVER (PARTITION BY title, part, type, identifier ORDER BY date DESC) AS n
    FROM version) v
  WHERE n = 1 AND NOT removed AND EXISTS (SELECT 1 FROM part p WHERE p.title = v.title AND p.part = v.part);

CREATE TABLE part_stale AS
  SELECT title, part, count(*) AS part_sections, CAST(sum(CAST(stale AS INT)) AS BIGINT) AS part_stale
  FROM section GROUP BY ALL;

CREATE TABLE ranked AS
  WITH x AS (
    SELECT p.title, p.part, p.ord, log10(p.words) AS x_size,
           CAST(1000 AS DOUBLE) * p.restrictions / p.words AS x_density,
           CAST(0.39 AS DOUBLE) * p.prose_words / p.sentences
             + CAST(11.8 AS DOUBLE) * p.syllables / p.prose_words - CAST(15.59 AS DOUBLE) AS x_grade,
           CAST(p.prohibition + p.paperwork + p.obligation AS DOUBLE) / p.sentences AS x_directive,
           CAST(p.paperwork AS DOUBLE) / p.sentences AS x_paperwork,
           coalesce(CAST(s.part_stale AS DOUBLE) / s.part_sections, 0) AS x_staleness
    FROM part p LEFT JOIN part_stale s USING (title, part) WHERE p.words >= 1000 AND p.sentences > 0),
  z AS (SELECT *, {z_columns} FROM x)
  SELECT *, ({z_sum}) / 6 AS score FROM z;

CREATE TABLE agency_metric AS
  SELECT a.*, coalesce(m.words, 0) AS words, coalesce(m.restrictions, 0) AS restrictions,
         CASE WHEN m.words > 0 THEN CAST(1000 AS DOUBLE) * m.restrictions / m.words END AS density,
         coalesce(m.parts, 0) AS parts, m.checksum,
         coalesce(old.checksum IS NOT NULL AND old.checksum <> m.checksum, false) AS changed,
         h.last_changed, coalesce(m.authority_words, '{zero}') AS authority_words,
         coalesce(st.sections, 0) AS sections, coalesce(st.stale_sections, 0) AS stale_sections,
         CASE WHEN st.sections > 0 THEN CAST(st.stale_sections AS DOUBLE) / st.sections END AS stale_share,
         {summed_columns}, coalesce(m.flagged_parts, 0) AS flagged_parts
  FROM agency a
  LEFT JOIN (SELECT ap.slug, CAST(sum(p.words) AS BIGINT) AS words,
                    CAST(sum(p.restrictions) AS BIGINT) AS restrictions, count(*) AS parts,
                    sha256(string_agg(p.title || '|' || p.part || '|' || p.hash || chr(10), '' ORDER BY p.title, p.ord))
                      AS checksum,
                    CAST(json_object({by_tag}) AS VARCHAR) AS authority_words,
                    {summed_sums}, count(*) FILTER (WHERE r.flagged) AS flagged_parts
             FROM agency_part ap JOIN part p USING (title, part) LEFT JOIN ranked_parts r USING (title, part)
             GROUP BY ap.slug) m USING (slug)
  LEFT JOIN (SELECT ap.slug, count(*) AS sections, CAST(sum(CAST(s.stale AS INT)) AS BIGINT) AS stale_sections
             FROM agency_part ap JOIN section s USING (title, part) GROUP BY ap.slug) st USING (slug)
  LEFT JOIN (SELECT ap.slug, max(v.date) AS last_changed FROM agency_part ap JOIN version v USING (title, part)
             GROUP BY ap.slug) h USING (slug)
  LEFT JOIN previous old USING (slug);
"""

RANK = """CREATE TABLE ranked_parts AS
  SELECT *, rank <= (count(*) OVER () + 9) // 10 AS flagged FROM (
    SELECT title, part, score, {inputs}, {zs},
           row_number() OVER (ORDER BY score DESC, title, ord) AS rank FROM ranked)"""


def analytics_sql(date):
    z = [
        f"coalesce((x_{c} - avg(x_{c}) OVER ()) / nullif(stddev_pop(x_{c}) OVER (), 0), 0) AS z_{c}"
        for c in INPUTS
    ]
    by_tag = ", ".join(
        f"'{t}', coalesce(sum(p.words) FILTER (WHERE p.authority = '{t}'), 0)" for t in TAGS
    )
    statements = ANALYTICS.format(
        date=date,
        cutoff=CUTOFF,
        z_columns=", ".join(z),
        z_sum=" + ".join(f"z_{c}" for c in INPUTS),
        zero=json.dumps(dict.fromkeys(TAGS, 0)),
        by_tag=by_tag,
        summed_columns=", ".join(f"coalesce(m.{c}, 0) AS {c}" for c in SUMMED),
        summed_sums=", ".join(f"CAST(sum(p.{c}) AS BIGINT) AS {c}" for c in SUMMED),
    ).split(";")
    rank = RANK.format(
        inputs=", ".join(f"x_{c}" for c in INPUTS), zs=", ".join(f"z_{c}" for c in INPUTS)
    )
    # agency_metric (last) needs ranked_parts, which needs ranked.
    return [s for s in statements[:-2] if s.strip()] + [rank, statements[-2]]


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def ingest(date, titles, full):
    date, doc = catalog(date)
    if doc["meta"]["import_in_progress"]:
        raise SystemExit("eCFR reports an import in progress; try again later")
    now = stamps(doc)
    titles = sorted(titles or now)
    prev = load_json(f"{STORE}/meta.json")
    incremental = bool(prev) and not full and prev.get("metrics_version") == METRICS_VERSION
    if incremental and prev["ecfr_date"] == date and prev["titles"] == titles:
        print(f"store is already at eCFR {date}; nothing to do")
        return
    # Build the new store next to the old one, then swap directories, so a failed ingest keeps the old data.
    # The build database is a file with a memory cap, so DuckDB spills to disk instead of holding all text in RAM.
    new = STORE + ".new"
    shutil.rmtree(new, ignore_errors=True)
    os.makedirs(f"{new}/text")
    db = duckdb.connect(f"{new}/build.duckdb")
    db.execute("SET memory_limit = '1GB'")
    db.execute(SCHEMA)
    if (
        prev
    ):  # yesterday's parts: reused when incremental, and always the baseline for the change log
        columns = NAMES if incremental else "title, part, heading, words, hash"
        db.execute(
            f"CREATE OR REPLACE TABLE prev_part AS SELECT {columns} FROM '{STORE}/parts.parquet'"
        )
    changed = titles
    if incremental:
        db.execute(
            f"INSERT INTO version_row SELECT * FROM '{STORE}/versions_all.parquet' WHERE list_contains(?, title)",
            [titles],
        )
        old = stamps(load_json(f"{STORE}/titles.json"))
        # A stored version that takes effect between the two snapshots can change a title's text
        # without moving its catalog dates, so those titles are reprocessed too.
        sql = "SELECT coalesce(list(DISTINCT title), []) FROM version_row WHERE date > ? AND date <= ?"
        activated = db.execute(sql, [prev["ecfr_date"], date]).fetchone()[0]
        changed = [
            n for n in titles if n not in prev["titles"] or old.get(n) != now[n] or n in activated
        ]
        keep = [n for n in titles if n not in changed]
        db.execute(
            f"INSERT INTO part SELECT {NAMES} FROM prev_part WHERE list_contains(?, title)", [keep]
        )
        for n in keep:
            shutil.copy2(f"{STORE}/text/title-{n}.parquet", f"{new}/text/title-{n}.parquet")
    since = {n: prev["ecfr_date"] if incremental and n in prev["titles"] else None for n in changed}
    raw, version_files = download(date, since)
    placeholders = ", ".join("?" * len(NAMES.split(", ")))
    for n in changed:
        # One file per statement: reading all versions files at once needed > 1 GB of JSON buffers.
        db.execute(f"""INSERT INTO version_row SELECT {n}, v.part, v.type, v.identifier,
                         CAST(v.date AS VARCHAR), v.substantive, v.removed
                       FROM (SELECT unnest(content_versions) AS v
                             FROM read_json('{version_files[n]}', maximum_object_size = 64000000))""")
        known = {}
        if incremental:
            rows = db.execute(
                f"SELECT part, prose_hash, {', '.join(SUMMED)} FROM prev_part WHERE title = ?", [n]
            )
            known = {(part, digest): tuple(counts) for part, digest, *counts in rows.fetchall()}
        db.execute("DELETE FROM part_text")
        for batch in itertools.batched(parse_parts(f"{raw}/title-{n}.xml.gz", n, known), 100):
            db.executemany(f"INSERT INTO part VALUES ({placeholders})", [row for row, _ in batch])
            db.executemany(
                "INSERT INTO part_text VALUES (?, ?, ?)", [(n, row[1], text) for row, text in batch]
            )
        db.execute(f"COPY part_text TO '{new}/text/title-{n}.parquet' {PARQUET}")
    with open(f"{raw}/agencies.json") as f:
        load_agencies(db, json.load(f)["agencies"])
    old = f"{STORE}/agencies.parquet"
    db.execute(
        f"CREATE TABLE previous AS SELECT slug, checksum FROM '{old}'"
        if os.path.exists(old)
        else "CREATE TABLE previous (slug VARCHAR, checksum VARCHAR)"
    )
    for statement in analytics_sql(date):
        db.execute(statement)
    dupes = db.sql("SELECT count(*) - count(DISTINCT (title, part)) FROM part").fetchone()[0]
    if dupes:
        raise SystemExit(f"{dupes} duplicate (title, part) keys")
    compare = (
        bool(prev) and date > prev["ecfr_date"]
    )  # log changes only when the snapshot moves forward
    db.execute(HISTORY.format(date=date, compare=compare, titles=titles))
    counts = dict(db.execute("SELECT change, count(*) FROM part_change GROUP BY change").fetchall())
    meta = build_meta(db, date, titles) | {
        "metrics_version": METRICS_VERSION,
        "mode": "incremental" if incremental else "full",
        "previous_ecfr_date": prev and prev["ecfr_date"],
        "titles_processed": changed,
        "parts_changed": {k: counts.get(k, 0) for k in ("added", "modified", "removed")},
    }
    exports = [
        (
            "SELECT p.*, s.part_sections, s.part_stale, r.* EXCLUDE (title, part) FROM part p "
            "LEFT JOIN part_stale s USING (title, part) LEFT JOIN ranked_parts r USING (title, part)",
            "parts",
        ),
        ("version", "versions"),
        ("version_all", "versions_all"),
        ("agency_part", "agency_parts"),
        ("agency_metric", "agencies"),
    ]
    for name, table, replace_date in (
        ("agency_history", "snapshot", True),
        ("part_changes", "part_change", compare),
    ):
        old = (
            f"{STORE}/{name}.parquet"  # history is append-only; a same-day rerun replaces snapshots
        )
        source = f"SELECT * FROM {table}"
        if prev and os.path.exists(old):
            source += f" UNION ALL SELECT * FROM '{old}'" + (
                f" WHERE ecfr_date <> '{date}'" if replace_date else ""
            )
        exports.append((f"{source} ORDER BY ALL", name))
    for source, name in exports:
        source = f"({source})" if source.startswith("SELECT") else source
        db.execute(f"COPY {source} TO '{new}/{name}.parquet' {PARQUET}")
    for name, value in (("meta", meta), ("titles", doc)):
        with open(f"{new}/{name}.json", "w") as f:
            json.dump(value, f)
    report(db, titles, meta)
    db.close()
    os.remove(f"{new}/build.duckdb")
    if os.path.exists(STORE):
        os.replace(STORE, STORE + ".old")
    os.replace(new, STORE)
    shutil.rmtree(STORE + ".old", ignore_errors=True)


PARQUET = "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 1000)"
HISTORY = """
CREATE TABLE snapshot AS
  SELECT '{date}' AS ecfr_date, slug, words, restrictions, parts, checksum, sections, stale_sections,
         flagged_parts
  FROM agency_metric;
CREATE TABLE part_change AS
  SELECT '{date}' AS ecfr_date, coalesce(n.title, o.title) AS title, coalesce(n.part, o.part) AS part,
         coalesce(n.heading, o.heading) AS heading,
         CASE WHEN o.part IS NULL THEN 'added' WHEN n.part IS NULL THEN 'removed' ELSE 'modified' END AS change,
         o.words AS words_before, n.words AS words_after
  FROM part n FULL JOIN (SELECT * FROM prev_part WHERE list_contains({titles}, title)) o
    ON n.title = o.title AND n.part = o.part
  WHERE {compare} AND n.hash IS DISTINCT FROM o.hash;
"""


def build_meta(db, date, titles):
    q = lambda sql: db.sql(sql).fetchone()[0]  # noqa: E731
    by_tag = ", ".join(
        f"'{t}', coalesce(sum(p.words) FILTER (WHERE p.authority = '{t}'), 0)" for t in TAGS
    )
    return {
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
        "eligible": q("SELECT count(*) FROM ranked_parts"),
    }


def report(db, titles, meta):
    print(f"{meta['parts']} parts, {meta['words']} words in parts, {meta['eligible']} ranked")
    print(f"{meta['mode']}: titles {meta['titles_processed']}, parts {meta['parts_changed']}")
    for slug, refs in db.sql("SELECT slug, refs FROM agency_metric WHERE parts = 0").fetchall():
        if any(r["title"] in titles for r in json.loads(refs)):
            print(f"warning: {slug} has refs in ingested titles but matched no parts")


# ---------- queries shared by the JSON API and the static export ----------

FIELDS = (
    "slug, name, short_name, parent_slug, words, restrictions, density, parts, checksum, changed, "
    "last_changed, authority_words, sections, stale_sections, stale_share, flagged_parts, "
    + ", ".join(SUMMED)
)


def ratio(a, b):
    return a / b if b else None


def agency_json(row):
    """API shape of an agency row: summed sentence counts become readability ratios and type counts."""
    s = {c: row[c] for c in SUMMED}
    readability = {
        "sentences": s["sentences"],
        "words_per_sentence": ratio(s["prose_words"], s["sentences"]),
        "fk_grade": (
            0.39 * s["prose_words"] / s["sentences"]
            + 11.8 * s["syllables"] / s["prose_words"]
            - 15.59
            if s["sentences"] and s["prose_words"]
            else None
        ),
        "long_share": ratio(s["long_sentences"], s["sentences"]),
        "passive_share": ratio(s["passive_sentences"], s["sentences"]),
        "crossrefs_per_1k": ratio(1000 * s["crossrefs"], s["prose_words"]),
    }
    base = {k: v for k, v in row.items() if k not in SUMMED and k not in ("refs", "children")}
    return {
        **base,
        "authority_words": json.loads(row["authority_words"]),
        "readability": readability,
        "sentence_types": {t: s[t] for t in TYPES},
    }


class NotFound(Exception):
    pass


def connect(store):
    con = duckdb.connect()
    for name in ("parts", "versions", "agency_parts", "agencies", "agency_history", "part_changes"):
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM '{store}/{name}.parquet'")
    return con


def query(con, sql, *args):
    cur = con.cursor()  # cursors make one DuckDB connection safe across FastAPI's threads
    cur.execute(sql, list(args))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def agency_row(con, slug):
    rows = query(con, f"SELECT {FIELDS}, refs, children FROM agencies WHERE slug = ?", slug)
    if not rows:
        raise NotFound(slug)
    return rows[0]


def agency_list(con):
    return [
        agency_json(r)
        for r in query(con, f"SELECT {FIELDS} FROM agencies ORDER BY words DESC, slug")
    ]


def agency_detail(con, slug):
    row = agency_row(con, slug)
    top = query(
        con,
        """SELECT p.title, p.part, p.heading, p.words, p.restrictions, p.authority FROM agency_parts ap
           JOIN parts p USING (title, part) WHERE ap.slug = ? ORDER BY p.words DESC, p.title, p.ord LIMIT 10""",
        slug,
    )
    statutes = query(
        con,
        """SELECT c.cite, count(*) AS parts, CAST(sum(c.words) AS BIGINT) AS words FROM agency_parts ap
           JOIN (SELECT title, part, words, unnest(cites) AS cite FROM parts) c USING (title, part)
           WHERE ap.slug = ? GROUP BY c.cite ORDER BY words DESC, c.cite LIMIT 10""",
        slug,
    )
    return {
        **agency_json(row),
        "refs": json.loads(row["refs"]),
        "children": json.loads(row["children"]),
        "top_parts": top,
        "top_statutes": statutes,
    }


def agency_history(con, slug):
    agency_row(con, slug)
    years = query(
        con,
        f"""SELECT CAST(substr(v.date, 1, 4) AS INT) AS year,
                   count(*) FILTER (WHERE NOT v.removed AND v.substantive) AS substantive,
                   count(*) FILTER (WHERE NOT v.removed AND NOT v.substantive) AS nonsubstantive,
                   count(*) FILTER (WHERE v.removed) AS removed
            FROM agency_parts ap JOIN versions v USING (title, part)
            WHERE ap.slug = ? AND v.date >= '{CUTOFF}' GROUP BY year ORDER BY year""",
        slug,
    )
    return {"slug": slug, "years": years}


def agency_trend(con, slug):
    """One row per daily refresh: the size and checksum of the agency's rules over time."""
    agency_row(con, slug)
    days = query(
        con,
        """SELECT ecfr_date AS date, words, restrictions, parts, checksum FROM agency_history
           WHERE slug = ? ORDER BY ecfr_date""",
        slug,
    )
    return {"slug": slug, "days": days}


def recent_changes(con, limit=200):
    rows = query(
        con, "SELECT * FROM part_changes ORDER BY ecfr_date DESC, title, part LIMIT ?", limit
    )
    return {"changes": rows}


def candidate_list(con, meta, agency=None, limit=50):
    if agency:
        agency_row(con, agency)
    scope = "JOIN agency_parts ap USING (title, part) WHERE ap.slug = ? AND" if agency else "WHERE"
    rows = query(
        con,
        f"""SELECT rank, title, part, heading, words, score, flagged, {", ".join(f"x_{c}" for c in INPUTS)},
                   {", ".join(f"z_{c}" for c in INPUTS)}
            FROM parts {scope} rank IS NOT NULL ORDER BY rank LIMIT ?""",
        *([agency] if agency else []),
        min(max(limit, 1), 500),
    )
    candidates = [
        {
            **{k: r[k] for k in ("rank", "title", "part", "heading", "words", "score", "flagged")},
            "inputs": {c: r[f"x_{c}"] for c in INPUTS},
            "z": {c: r[f"z_{c}"] for c in INPUTS},
        }
        for r in rows
    ]
    n = meta["eligible"]
    return {"agency": agency, "eligible": n, "flagged": (n + 9) // 10, "candidates": candidates}


# ---------- static site: the same queries written as files, for GitHub Pages ----------

STATIC_API = {
    "meta": "Snapshot metadata, last refresh, and what the last refresh changed",
    "agencies": "All agencies with metrics",
    "agencies/{slug}": "One agency with references, sub-agencies, largest parts and statutes",
    "agencies/{slug}/history": "Recorded section changes per year since 2017",
    "agencies/{slug}/trend": "Daily snapshots: words, restrictions, parts, checksum",
    "candidates": "Top 500 review candidates",
    "candidates/{slug}": "Top 500 review candidates within one agency",
    "changes": "The 200 most recent part changes (added, modified, removed)",
}
RESPONSES = {
    "200": {"description": "JSON, same shape as the live API route without .json"},
    "404": {"description": "GitHub Pages HTML error page (not JSON)"},
}


def export(out):
    import jinja2

    con, meta = connect(STORE), load_json(f"{STORE}/meta.json")
    env = jinja2.Environment(loader=jinja2.FileSystemLoader("app/templates"), autoescape=True)
    env.filters.update(
        num=lambda n: "—" if n is None else f"{n:,}",
        f1=lambda x: "—" if x is None else f"{x:.1f}",
        pct=lambda x: "—" if x is None else f"{100 * x:.1f}%",
    )
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree("app/static", f"{out}/static")
    # Asset URLs carry a content hash so browsers and the Pages CDN never serve stale JS/CSS.
    digest = hashlib.sha256()
    for name in sorted(os.listdir("app/static")):
        digest.update(open(f"app/static/{name}", "rb").read())
    shutil.copytree(
        STORE, f"{out}/data", ignore=shutil.ignore_patterns("versions_all.parquet", "titles.json")
    )

    def write(path, text):  # paths contain agency slugs from eCFR data: never write outside out/
        target = os.path.realpath(f"{out}/{path}")
        if not target.startswith(os.path.realpath(out) + os.sep):
            raise SystemExit(f"refusing to write outside {out}: {path!r}")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w") as f:
            f.write(text)

    def api(path, value):
        write(f"api/{path}.json", json.dumps(value))

    version = digest.hexdigest()[:10]

    def page(path, template, **context):
        write(path, env.get_template(template).render(meta=meta, version=version, **context))

    agencies = agency_list(con)
    top = candidate_list(con, meta, None, 500)
    api("meta", meta)
    api("agencies", agencies)
    api("candidates", top)
    api("changes", recent_changes(con))
    paths = {
        f"/api/{p}.json": {"get": {"summary": t, "responses": RESPONSES}}
        for p, t in STATIC_API.items()
    }
    info = {"title": "eCFR analyzer static API", "version": meta["ecfr_date"]}
    api("openapi", {"openapi": "3.1.0", "info": info, "paths": paths})
    for a in agencies:
        slug = a["slug"]
        detail = agency_detail(con, slug)
        years, trend = agency_history(con, slug), agency_trend(con, slug)
        candidates = candidate_list(con, meta, slug, 500)
        for path, value in ((slug, detail), (f"{slug}/history", years), (f"{slug}/trend", trend)):
            api(f"agencies/{path}", value)
        api(f"candidates/{slug}", candidates)
        first = {**candidates, "candidates": candidates["candidates"][:25]}
        page(f"ui/candidates/{slug}.html", "candidates.html", candidates=first)
        page(
            f"ui/agency/{slug}.html",
            "detail.html",
            a=detail,
            history=years["years"],
            trend=trend["days"],
            candidates={**candidates, "candidates": candidates["candidates"][:5]},
        )
    first = {**top, "candidates": top["candidates"][:25]}
    page("ui/candidates/all.html", "candidates.html", candidates=first)
    top_level = [a for a in agencies if not a["parent_slug"]]
    page(
        "index.html",
        "index.html",
        rows=[
            r
            for p in top_level
            for r in [p] + [c for c in agencies if c["parent_slug"] == p["slug"]]
        ],
        scatter=[
            [a["short_name"] or a["name"], a["words"], a["density"], a["slug"]]
            for a in top_level
            if a["words"] >= 1000
        ],
        candidates=first,
        changes=recent_changes(con, 50)["changes"],
        filters=[a for a in agencies if a["flagged_parts"]],
    )
    print(f"exported {out}/ for eCFR {meta['ecfr_date']} ({len(agencies)} agencies)")


def serve(port, site):
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(title="eCFR analyzer API")
    con, meta = connect(STORE), load_json(f"{STORE}/meta.json")

    def call(fn, *args):
        try:
            return fn(con, *args)
        except NotFound:
            raise HTTPException(404, "not found") from None

    app.get("/api/meta")(lambda: meta)

    @app.get("/api/agencies")
    def api_agencies():
        return call(agency_list)

    @app.get("/api/agencies/{slug}")
    def api_agency(slug: str):  # also answers the static path /api/agencies/<slug>.json
        return call(agency_detail, slug.removesuffix(".json"))

    @app.get("/api/agencies/{slug}/history")
    def api_history(slug: str):
        return call(agency_history, slug)

    @app.get("/api/agencies/{slug}/trend")
    def api_trend(slug: str):
        return call(agency_trend, slug)

    @app.get("/api/candidates")
    def api_candidates(agency: str | None = None, limit: int = 50):
        return call(candidate_list, meta, agency, limit)

    @app.get("/api/changes")
    def api_changes(limit: int = 200):
        return call(recent_changes, min(max(limit, 1), 1000))

    # Everything else is the exported static site: pages, JSON files and Parquet.
    app.mount("/", StaticFiles(directory=site, html=True), name="site")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    cli.add_argument("--store", default=STORE)
    sub = cli.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest")
    ing.add_argument("--date")
    ing.add_argument("--titles", type=lambda s: [int(t) for t in s.split(",")], default=[])
    ing.add_argument(
        "--full", action="store_true", help="reprocess every title instead of only changed ones"
    )
    sub.add_parser("export").add_argument("--out", default="site")
    srv = sub.add_parser("serve")
    srv.add_argument("--port", type=int, default=8310)
    srv.add_argument("--site", default="site")
    args = cli.parse_args()
    STORE = args.store
    commands = {
        "ingest": lambda: ingest(args.date, args.titles, args.full),
        "export": lambda: export(args.out),
        "serve": lambda: serve(args.port, args.site),
    }
    commands[args.cmd]()
