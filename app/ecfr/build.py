"""Build the Parquet store with DuckDB: incremental ingest, analytics, ranking and history."""

import itertools
import json
import os
import shutil
from datetime import datetime, timezone

import duckdb

from .model import CUTOFF, INPUTS
from .parse import parse_parts
from .source import catalog, download, load_json, stamps
from .text import SUMMED, TAGS

METRICS_VERSION = "r3"  # bump when per-part metrics change: stored metrics are then recomputed
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


def ingest(store, date, titles, full):
    date, doc = catalog(date)
    if doc["meta"]["import_in_progress"]:
        raise SystemExit("eCFR reports an import in progress; try again later")
    now = stamps(doc)
    titles = sorted(titles or now)
    prev = load_json(f"{store}/meta.json")
    incremental = bool(prev) and not full and prev.get("metrics_version") == METRICS_VERSION
    if incremental and prev["ecfr_date"] == date and prev["titles"] == titles:
        print(f"store is already at eCFR {date}; nothing to do")
        return
    # Build the new store next to the old one, then swap directories, so a failed ingest keeps the old data.
    # The build database is a file with a memory cap, so DuckDB spills to disk instead of holding all text in RAM.
    new = store + ".new"
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
            f"CREATE OR REPLACE TABLE prev_part AS SELECT {columns} FROM '{store}/parts.parquet'"
        )
    changed = titles
    if incremental:
        db.execute(
            f"INSERT INTO version_row SELECT * FROM '{store}/versions_all.parquet' WHERE list_contains(?, title)",
            [titles],
        )
        old = stamps(load_json(f"{store}/titles.json"))
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
            shutil.copy2(f"{store}/text/title-{n}.parquet", f"{new}/text/title-{n}.parquet")
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
    old = f"{store}/agencies.parquet"
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
            f"{store}/{name}.parquet"  # history is append-only; a same-day rerun replaces snapshots
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
    if os.path.exists(store):
        os.replace(store, store + ".old")
    os.replace(new, store)
    shutil.rmtree(store + ".old", ignore_errors=True)


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
