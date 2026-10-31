"""Diff every API route between variants. Usage: python bench/parity.py 8301 8302 [8303]"""

import json
import sys
import urllib.request
from collections import Counter


def get(port, path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=60) as r:
            return [r.status, json.loads(r.read())]
    except urllib.error.HTTPError as e:
        return [e.code, json.loads(e.read() or b"null")]


def diff(a, b, path=""):
    """Yield (path, a, b) for every leaf that differs."""
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k != "ingested_at":
                yield from diff(a.get(k, "<missing>"), b.get(k, "<missing>"), f"{path}.{k}")
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            yield from diff(x, y, f"{path}[{i}]")
    elif a != b or type(a) is not type(b):
        yield path, a, b


def main(ports):
    ref = ports[0]
    slugs = [a["slug"] for a in get(ref, "/api/agencies")[1]]
    routes = [
        "/api/meta",
        "/api/agencies",
        "/api/agencies/does-not-exist",
        "/api/agencies/does-not-exist/history",
    ]
    routes += [f"/api/agencies/{s}" for s in slugs] + [f"/api/agencies/{s}/history" for s in slugs]
    expected = {route: get(ref, route) for route in routes}
    ok = True
    for port in ports[1:]:
        fields, examples, bad_routes = Counter(), {}, 0
        for route in routes:
            got = get(port, route)
            found = list(diff(expected[route], got))
            if found:
                bad_routes += 1
                for path, a, b in found:
                    field = route.split("/")[2] + ":" + "".join(c for c in path if not c.isdigit())
                    fields[field] += 1
                    examples.setdefault(field, (route, path, a, b))
        print(f"{ref} vs {port}: {len(routes) - bad_routes}/{len(routes)} routes identical")
        for field, n in fields.most_common():
            route, path, a, b = examples[field]
            print(
                f"  {n:6} diffs in {field}   e.g. {route} {path}: {str(a)[:60]!r} vs {str(b)[:60]!r}"
            )
        ok &= not fields
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main([int(p) for p in sys.argv[1:]])
