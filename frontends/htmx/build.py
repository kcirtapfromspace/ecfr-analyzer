"""Static generator for the htmx slice: pre-render index.html and one fragment per agency from the fixtures.

Usage: uv run --with jinja2==3.1.4 python build.py
"""

import json
import pathlib
import shutil

import jinja2

HERE = pathlib.Path(__file__).parent
API = HERE.parent / "fixtures/api"
OUT = HERE / "dist"

env = jinja2.Environment(loader=jinja2.FileSystemLoader(HERE / "templates"), autoescape=True)
env.filters.update(
    num=lambda n: "—" if n is None else f"{n:,}",
    f1=lambda x: "—" if x is None else f"{x:.1f}",
    pct=lambda x: "—" if x is None else f"{100 * x:.1f}%",
)

agencies = json.loads((API / "agencies.json").read_text())
top = [a for a in agencies if not a["parent_slug"]]
shutil.rmtree(OUT, ignore_errors=True)
shutil.copytree(HERE / "static", OUT / "static")
(OUT / "agency").mkdir()
(OUT / "index.html").write_text(
    env.get_template("index.html").render(
        rows=[r for p in top for r in [p] + [c for c in agencies if c["parent_slug"] == p["slug"]]],
        scatter=[[a["name"], a["words"], a["density"], a["slug"]] for a in top if a["words"] >= 1000],
    )
)
for a in agencies:
    detail = json.loads((API / f"agencies/{a['slug']}.json").read_text())
    years = json.loads((API / f"agencies/{a['slug']}/history.json").read_text())["years"]
    page = env.get_template("detail.html").render(a=detail, years=years)
    (OUT / f"agency/{a['slug']}.html").write_text(page)
