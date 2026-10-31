"""Static site export for GitHub Pages: JSON API files, htmx fragments and the Parquet data."""

import hashlib
import json
import os
import shutil

import jinja2

from . import queries
from ..core.model import load_json

HERE = os.path.dirname(os.path.abspath(__file__))  # templates/ and static/ ship inside the package
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


def export(store, out):
    con, meta = queries.connect(store), load_json(f"{store}/meta.json")
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(f"{HERE}/templates"), autoescape=True)
    env.filters.update(
        num=lambda n: "—" if n is None else f"{n:,}",
        f1=lambda x: "—" if x is None else f"{x:.1f}",
        pct=lambda x: "—" if x is None else f"{100 * x:.1f}%",
    )
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(f"{HERE}/static", f"{out}/static")
    # Asset URLs carry a content hash so browsers and the Pages CDN never serve stale JS/CSS.
    digest = hashlib.sha256()
    for name in sorted(os.listdir(f"{HERE}/static")):
        digest.update(open(f"{HERE}/static/{name}", "rb").read())
    shutil.copytree(
        store, f"{out}/data", ignore=shutil.ignore_patterns("versions_all.parquet", "titles.json")
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

    agencies = queries.agency_list(con)
    top = queries.candidate_list(con, meta, None, 500)
    api("meta", meta)
    api("agencies", agencies)
    api("candidates", top)
    api("changes", queries.recent_changes(con))
    paths = {
        f"/api/{p}.json": {"get": {"summary": t, "responses": RESPONSES}}
        for p, t in STATIC_API.items()
    }
    info = {"title": "eCFR analyzer static API", "version": meta["ecfr_date"]}
    api("openapi", {"openapi": "3.1.0", "info": info, "paths": paths})
    for a in agencies:
        slug = a["slug"]
        detail = queries.agency_detail(con, slug)
        years, trend = queries.agency_history(con, slug), queries.agency_trend(con, slug)
        candidates = queries.candidate_list(con, meta, slug, 500)
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
        changes=queries.recent_changes(con, 50)["changes"],
        filters=[a for a in agencies if a["flagged_parts"]],
    )
    print(f"exported {out}/ for eCFR {meta['ecfr_date']} ({len(agencies)} agencies)")
