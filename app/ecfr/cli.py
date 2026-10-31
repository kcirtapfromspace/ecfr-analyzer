"""Command line: uv run ecfr [--store data/app] ingest|export|serve (run from the repository root).

ingest [--date D] [--titles 1,40] [--full]   incremental against the store unless --full
export [--out site]                          static site: pages, JSON API, Parquet
serve [--port 8310] [--site site]            JSON API (+ /docs) serving the exported site
"""

import argparse

from .api import serve
from .build import ingest
from .site import export


def main():
    cli = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    cli.add_argument("--store", default="data/app")
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
    if args.cmd == "ingest":
        ingest(args.store, args.date, args.titles, args.full)
    elif args.cmd == "export":
        export(args.store, args.out)
    else:
        serve(args.store, args.site, args.port)
