"""eCFR API client and raw-file cache (data/raw/{date}/), used by every ingest."""

import concurrent.futures as cf
import json
import os
import time
import urllib.request

from ..core.model import load_json

API = "https://www.ecfr.gov/api"


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
