"""Static site export for GitHub Pages: the page, its JSON API files and the Parquet data."""

import hashlib
import json
import os
import shutil

from . import queries
from .source import load_json

STATIC = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static"
)  # ships inside the package
STATIC_API = {
    "meta": "Snapshot metadata, last refresh, and what the last refresh changed",
    "agencies": "All agencies with metrics",
    "agency-table": "All agencies, only the columns of the index table",
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
UI_CANDIDATES = 25  # rows the page shows; ui/candidates/*.json equal /api/candidates?limit=25


def export(store, out):
    con, meta = queries.connect(store), load_json(f"{store}/meta.json")
    shutil.rmtree(out, ignore_errors=True)
    # Assets live under a content-hash directory, so browsers and the Pages CDN never serve stale
    # JS/CSS, including modules that app.js imports by relative path.
    digest = hashlib.sha256()
    for name in sorted(os.listdir(STATIC)):
        digest.update(open(f"{STATIC}/{name}", "rb").read())
    version = digest.hexdigest()[:10]
    shutil.copytree(STATIC, f"{out}/static/{version}", ignore=shutil.ignore_patterns("index.html"))
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

    def ui(path, candidates):
        write(
            f"ui/candidates/{path}.json",
            json.dumps({**candidates, "candidates": candidates["candidates"][:UI_CANDIDATES]}),
        )

    agencies = queries.agency_list(con)
    top = queries.candidate_list(con, meta, None, 500)
    api("meta", meta)
    api("agencies", agencies)
    api("agency-table", queries.agency_table(con))
    api("candidates", top)
    ui("all", top)
    api("changes", queries.recent_changes(con))
    paths = {
        f"/api/{p}.json": {"get": {"summary": t, "responses": RESPONSES}}
        for p, t in STATIC_API.items()
    }
    info = {"title": "eCFR analyzer static API", "version": meta["ecfr_date"]}
    api("openapi", {"openapi": "3.1.0", "info": info, "paths": paths})
    for a in agencies:
        slug = a["slug"]
        api(f"agencies/{slug}", queries.agency_detail(con, slug))
        api(f"agencies/{slug}/history", queries.agency_history(con, slug))
        api(f"agencies/{slug}/trend", queries.agency_trend(con, slug))
        candidates = queries.candidate_list(con, meta, slug, 500)
        api(f"candidates/{slug}", candidates)
        ui(slug, candidates)
    write("index.html", open(f"{STATIC}/index.html").read().replace("__VERSION__", version))
    print(f"exported {out}/ for eCFR {meta['ecfr_date']} ({len(agencies)} agencies)")
