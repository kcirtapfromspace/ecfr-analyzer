"""Read queries over a Parquet store, shared by the JSON API and the static export."""

import json

import duckdb

from .model import CUTOFF, INPUTS
from .text import SUMMED, TYPES

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
