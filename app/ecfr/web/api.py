"""FastAPI JSON API over a store; everything else is served from the exported static site."""

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from . import queries
from ..core.model import load_json


def create_app(store, site):
    app = FastAPI(title="eCFR analyzer API")
    con, meta = queries.connect(store), load_json(f"{store}/meta.json")

    def call(fn, *args):
        try:
            return fn(con, *args)
        except queries.NotFound:
            raise HTTPException(404, "not found") from None

    app.get("/api/meta")(lambda: meta)

    @app.get("/api/agencies")
    def api_agencies():
        return call(queries.agency_list)

    @app.get("/api/agencies/{slug}")
    def api_agency(slug: str):  # also answers the static path /api/agencies/<slug>.json
        return call(queries.agency_detail, slug.removesuffix(".json"))

    @app.get("/api/agencies/{slug}/history")
    def api_history(slug: str):
        return call(queries.agency_history, slug)

    @app.get("/api/agencies/{slug}/trend")
    def api_trend(slug: str):
        return call(queries.agency_trend, slug)

    @app.get("/api/candidates")
    def api_candidates(agency: str | None = None, limit: int = 50):
        return call(queries.candidate_list, meta, agency, limit)

    @app.get("/api/changes")
    def api_changes(limit: int = 200):
        return call(queries.recent_changes, min(max(limit, 1), 1000))

    # Everything else is the exported static site: pages, JSON files and Parquet.
    app.mount("/", StaticFiles(directory=site, html=True), name="site")
    return app


def serve(store, site, port):
    uvicorn.run(create_app(store, site), host="127.0.0.1", port=port, log_level="warning")
