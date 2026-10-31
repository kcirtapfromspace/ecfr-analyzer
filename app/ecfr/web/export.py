"""Static site export for GitHub Pages: the pages, the JSON API as files, and the Parquet data."""

import hashlib
import json
import os
import shutil

import jinja2

from . import queries
from ..core.model import INPUTS, load_json

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
        heading=lambda h: (h or "").split("—", 1)[
            -1
        ],  # "PART 63—NATIONAL ..." without the repeated part number
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

    agencies = queries.agency_list(con)
    by_slug = {a["slug"]: a for a in agencies}

    def page(path, template, **context):  # root: the way back from the page to the site root
        root = "../" * path.count("/") or "./"
        context |= dict(meta=meta, version=version, agencies=agencies, metrics=INPUTS, root=root)
        write(path, env.get_template(template).render(**context))

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
        page(
            f"agency/{slug}/index.html",
            "agency.html",
            a=detail,
            parent=by_slug.get(detail["parent_slug"]),
            children=[by_slug[c] for c in detail["children"]],
            history=years["years"],
            trend=trend["days"],
            candidates={**candidates, "candidates": candidates["candidates"][:25]},
        )
    page(
        "index.html",
        "index.html",
        scatter=[
            [a["short_name"] or a["name"], a["words"], a["density"], a["slug"]]
            for a in agencies
            if not a["parent_slug"] and a["words"] >= 1000
        ],
        candidates={**top, "candidates": top["candidates"][:25]},
        changes=queries.recent_changes(con, 50)["changes"],
    )
    page("explore/index.html", "explore.html")
    print(f"exported {out}/ for eCFR {meta['ecfr_date']} ({len(agencies)} agencies)")
