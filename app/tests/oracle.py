#!/usr/bin/env python3
"""Independent oracle for the metric contract (CONTRACT.md at tag v0.2.0); standard library and raw cache only.

Run from the repository root with uv run app/tests/oracle.py
--dump expected.json and/or --base http://127.0.0.1:PORT. No application,
H1, or H2 code is imported or consulted. No download or store is needed.

Dump schema: snapshot, titles, parts (all raw/derived Round 3 part metrics),
agencies (slug-keyed Round 3 fields), eligible, flagged, candidates (full list).

Interpretations where the contract leaves room:
* Candidate metadata and ranks remain global under an agency filter.
* Rejoin split pieces before dropping wordless pieces (numbered step order).
* Population moments use two passes with math.fsum; summation order is not
  prescribed. Rank exceptions use pairwise isclose, never transitive groups.
* Only ranks/list order get the near-score exception; flags stay exact, even
  at the 10% cutoff. Filter/limit boundaries permit the same pairwise swaps.
* The dump layout is chosen here because the contract specifies no layout.
"""

import argparse
from functools import lru_cache
import gzip
import json
import math
from pathlib import Path
import re
import sys
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
import xml.etree.ElementTree as ET


WORD = re.compile(r"[^\W_]+")
RESTRICTION = re.compile(r"\b(shall|must|may not|required|prohibited)\b")
SPLIT = re.compile(r'(?<=[.?!])\s+(?=[A-Z(§"“])')
ABBREVIATION = re.compile(
    r"(?:^|[\s(])(?:U\.S\.C|U\.S|e\.g|i\.e|etc|et seq|No|Nos|Sec|Secs|"
    r"Pub|L|Stat|Fed|Reg|Inc|Co|Corp|Ltd|Dr|Mr|Mrs|Ms|St|Jr|Vol|Ch|Pt|App|"
    r"cf|al|approx|ft|in|lb|lbs|oz|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|"
    r"Nov|Dec|[A-Z])\.$"
)
VOWELS = re.compile(r"[aeiouy]+")
PASSIVE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?\w+(?:ed|en)\b")
CROSSREF = re.compile(r"§|\bparagraphs? \(|\bsections? \d|\bparts? \d|\bsubparts? [a-z]\b|u\.s\.c\.")
DEFINITION = re.compile(r"\b(?:means|is defined as|has the meaning|have the meaning|as used in this)\b")
PROHIBITION = re.compile(r"\b(?:shall not|must not|may not|is prohibited|are prohibited|prohibited from|no person shall|no person may)\b")
REQUIRED = re.compile(r"\b(?:shall|must|is required to|are required to)\b")
PAPERWORK = re.compile(r"\b(?:report|reports|record|records|recordkeeping|submit|submits|submitted|notify|notification|certify|certification|application|apply|file|filing|disclose|disclosure|form|forms)\b")
OBLIGATION = re.compile(r"\b(?:shall|must|is required to|are required to|required)\b")
PERMISSION = re.compile(r"\bmay\b")
TYPES = ("definition", "prohibition", "paperwork", "obligation", "permission", "other")
INPUTS = ("size", "density", "grade", "directive", "paperwork", "staleness")
COUNTS = ("prose_words", "sentences", "syllables", "long_sentences", "passive_sentences", "crossrefs")
ANCESTORS = {"SUBTITLE": "subtitle", "CHAPTER": "chapter", "SUBCHAP": "subchapter"}
REL_TOL, ABS_TOL = 1e-9, 1e-12
FETCH_FAILED = object()


def normalize(pieces):
    return " ".join(unicodedata.normalize("NFC", " ".join(pieces)).split())


def prose_nodes(element):
    if element.tag in ("TABLE", "MATH"):
        return
    if element.text is not None:
        yield element.text
    for child in element:
        yield from prose_nodes(child)
        if child.tail is not None:
            yield child.tail


def sentences(text):
    kept = []
    for piece in SPLIT.split(text):
        if kept and ABBREVIATION.search(kept[-1]):
            kept[-1] += " " + piece
        else:
            kept.append(piece)
    return [piece for piece in kept if WORD.search(piece)]


@lru_cache(maxsize=131072)
def syllables(word):
    return max(1, len(VOWELS.findall(word.lower())))


def classify(sentence):
    text = sentence.lower()
    if DEFINITION.search(text):
        return "definition"
    if PROHIBITION.search(text):
        return "prohibition"
    if REQUIRED.search(text) and PAPERWORK.search(text):
        return "paperwork"
    if OBLIGATION.search(text):
        return "obligation"
    return "permission" if PERMISSION.search(text) else "other"


def readability(counts):
    words, count = counts["prose_words"], counts["sentences"]
    return {
        "sentences": count,
        "words_per_sentence": words / count if count else None,
        "fk_grade": 0.39 * words / count + 11.8 * counts["syllables"] / words - 15.59 if words and count else None,
        "long_share": counts["long_sentences"] / count if count else None,
        "passive_share": counts["passive_sentences"] / count if count else None,
        "crossrefs_per_1k": 1000.0 * counts["crossrefs"] / words if words else None,
    }


def measure(element):
    text = normalize(element.itertext())
    prose = normalize(prose_nodes(element))
    split = sentences(prose)
    counts = {key: 0 for key in COUNTS}
    counts.update(words=sum(1 for _ in WORD.finditer(text)),
                  restrictions=len(RESTRICTION.findall(text.lower())),
                  sentences=len(split), crossrefs=len(CROSSREF.findall(prose.lower())))
    for match in WORD.finditer(prose):
        counts["prose_words"] += 1
        counts["syllables"] += syllables(match.group())
    types = dict.fromkeys(TYPES, 0)
    for sentence in split:
        types[classify(sentence)] += 1
        counts["long_sentences"] += sum(1 for _ in WORD.finditer(sentence)) > 40
        counts["passive_sentences"] += bool(PASSIVE.search(sentence.lower()))
    counts["sentence_types"] = types
    counts["readability"] = readability(counts)
    return counts


def part_staleness(path, snapshot):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data["content_versions"]
    if len(rows) != data["result_count"]:
        raise ValueError(f"{path}: result_count does not match cached rows")
    latest = {}
    for row in rows:
        if row["date"] > snapshot:
            continue
        key = (row["part"], row["type"], row["identifier"])
        previous = latest.get(key)
        if previous is None or row["date"] > previous[0]:
            latest[key] = (row["date"], row["removed"])
        elif row["date"] == previous[0]:
            # OR on duplicate latest dates is equivalent to full dedup first;
            # substantive is irrelevant to current/stale status.
            latest[key] = (previous[0], previous[1] or row["removed"])
    counts = {}
    for (part, _, _), (date, removed) in latest.items():
        if not removed and part is not None:
            current, stale = counts.get(part, (0, 0))
            counts[part] = (current + 1, stale + (date < "2017-01-01"))
    return counts


def title_parts(raw, title, snapshot):
    staleness = part_staleness(raw / f"versions-{title}.json", snapshot)
    stack, ordinals = [], {}
    active, ordinal = 0, 0
    with gzip.open(raw / f"title-{title}.xml.gz", "rb") as source:
        for event, element in ET.iterparse(source, events=("start", "end")):
            is_part = element.get("TYPE") == "PART"
            if event == "start":
                stack.append(element)
                if is_part:
                    ordinals[id(element)] = ordinal
                    ordinal += 1
                    active += 1
                continue
            if is_part:
                part = {"title": title, "part": element.attrib["N"],
                        "ord": ordinals.pop(id(element)),
                        "subtitle": None, "chapter": None, "subchapter": None}
                for ancestor in stack[:-1]:
                    if ancestor.get("TYPE") in ANCESTORS:
                        part[ANCESTORS[ancestor.get("TYPE")]] = ancestor.get("N")
                heading = next((child for child in element if child.tag == "HEAD"), None)
                part["heading"] = normalize(heading.itertext()) if heading is not None else ""
                part.update(measure(element))
                current, stale = staleness.get(part["part"], (0, 0))
                part.update(part_sections=current, part_stale=stale,
                            part_stale_share=stale / current if current else None)
                yield part
                active -= 1
            if active == 0:
                element.clear()
                if len(stack) > 1:
                    stack[-2].remove(element)
            stack.pop()


def rank_parts(parts):
    eligible = [part for part in parts if part["words"] >= 1000 and part["sentences"] > 0]
    for part in parts:
        part.update(rank=None, flagged=False)
    for part in eligible:
        types, count = part["sentence_types"], part["sentences"]
        part["inputs"] = {
            "size": math.log10(part["words"]),
            "density": 1000.0 * part["restrictions"] / part["words"],
            "grade": 0.39 * part["prose_words"] / count + 11.8 * part["syllables"] / part["prose_words"] - 15.59,
            "directive": sum(types[k] for k in ("prohibition", "paperwork", "obligation")) / count,
            "paperwork": types["paperwork"] / count,
            "staleness": part["part_stale_share"] if part["part_stale_share"] is not None else 0.0,
        }
    if not eligible:
        return []
    moments = {}
    for name in INPUTS:
        values = [part["inputs"][name] for part in eligible]
        mean = math.fsum(values) / len(values)
        std = math.sqrt(math.fsum((value - mean) ** 2 for value in values) / len(values))
        moments[name] = (mean, std)
    for part in eligible:
        part["z"] = {name: (part["inputs"][name] - mean) / std if std else 0.0
                     for name, (mean, std) in moments.items()}
        part["score"] = math.fsum(part["z"].values()) / len(INPUTS)
    eligible.sort(key=lambda part: (-part["score"], part["title"], part["ord"]))
    cutoff = math.ceil(0.10 * len(eligible))
    candidates = []
    for rank, part in enumerate(eligible, 1):
        part.update(rank=rank, flagged=rank <= cutoff)
        candidates.append({key: part[key] for key in
                           ("rank", "title", "part", "heading", "words", "score", "flagged", "inputs", "z")})
    return candidates


def agency_sets(raw, parts):
    roots = json.loads((raw / "agencies.json").read_text(encoding="utf-8"))["agencies"]
    by_title = {}
    for index, part in enumerate(parts):
        by_title.setdefault(part["title"], []).append(index)
    sets = {}
    for root in roots:
        family = [root] + root.get("children", [])
        for agency in family:
            own = set()
            for ref in agency["cfr_references"]:
                for index in by_title.get(ref["title"], []):
                    if all(parts[index][key] == ref[key] for key in ("subtitle", "chapter", "subchapter", "part") if key in ref):
                        own.add(index)
            if agency["slug"] in sets:
                raise ValueError(f"duplicate agency slug: {agency['slug']}")
            sets[agency["slug"]] = own
        for child in root.get("children", []):
            sets[root["slug"]].update(sets[child["slug"]])
    return sets


def build_expected(raw, snapshot):
    source = json.loads((raw / "titles.json").read_text(encoding="utf-8"))
    if source["meta"]["import_in_progress"]:
        raise ValueError("titles.json: import_in_progress is true")
    titles = sorted(row["number"] for row in source["titles"] if not row["reserved"])
    parts = []
    keys = set()
    for title in titles:
        for part in title_parts(raw, title, snapshot):
            key = (title, part["part"])
            if key in keys:
                raise ValueError(f"duplicate part key: {key}")
            keys.add(key)
            parts.append(part)
        print(f"Title {title}: processed; {len(parts)} parts so far", file=sys.stderr, flush=True)
    candidates = rank_parts(parts)
    memberships = agency_sets(raw, parts)
    agencies = {}
    for slug, members in sorted(memberships.items()):
        counts = {key: sum(parts[i][key] for i in sorted(members)) for key in COUNTS}
        agencies[slug] = {
            "readability": readability(counts),
            "sentence_types": {key: sum(parts[i]["sentence_types"][key] for i in sorted(members)) for key in TYPES},
            "flagged_parts": sum(parts[i]["flagged"] for i in members),
        }
    expected = {"snapshot": snapshot, "titles": titles, "parts": parts, "agencies": agencies,
                "eligible": len(candidates), "flagged": math.ceil(0.10 * len(candidates)),
                "candidates": candidates}
    member_keys = {slug: {(parts[i]["title"], parts[i]["part"]) for i in members}
                   for slug, members in memberships.items()}
    return expected, member_keys


def close(a, b):
    if type(a) not in (int, float) or type(b) not in (int, float):
        return False
    try:
        return (math.isfinite(a) and math.isfinite(b)
                and math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL))
    except OverflowError:
        return False


class Mismatches:
    def __init__(self):
        self.fields = {}

    def add(self, field, context, expected, actual):
        entry = self.fields.setdefault(field, {"count": 0, "examples": []})
        entry["count"] += 1
        if len(entry["examples"]) < 3:
            entry["examples"].append(f"{context}: expected {expected!r}; got {actual!r}"[:600])

    def compare(self, expected, actual, field, context):
        if isinstance(expected, dict):
            if not isinstance(actual, dict):
                self.add(field, context, "object", actual)
                return
            for key in sorted(expected.keys() | actual.keys()):
                if key not in expected or key not in actual:
                    self.add(f"{field}.{key}", context, expected.get(key, "<absent>"), actual.get(key, "<absent>"))
                else:
                    self.compare(expected[key], actual[key], f"{field}.{key}", context)
        elif isinstance(expected, float):
            if not close(expected, actual):
                self.add(field, context, expected, actual)
        elif type(expected) is not type(actual) or expected != actual:
            self.add(field, context, expected, actual)

    def summary(self):
        total = sum(entry["count"] for entry in self.fields.values())
        print(f"Comparison: {total} mismatch(es) across {len(self.fields)} field(s).")
        for field, entry in sorted(self.fields.items()):
            print(f"  {field}: {entry['count']}")
            for example in entry["examples"]:
                print(f"    {example}")
        return total


def fetch(base, route, mismatches):
    try:
        with urlopen(base.rstrip("/") + route, timeout=60) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        mismatches.add("http", route, "HTTP 200 with JSON", str(exc))
        return FETCH_FAILED


def compare_candidates(payload, expected, selected, context, mismatches):
    if not isinstance(payload, dict):
        mismatches.add("candidates.response", context, "object", payload)
        return
    slug = None if context == "global" else context
    for field, value in (("agency", slug), ("eligible", expected["eligible"]), ("flagged", expected["flagged"])):
        if field not in payload:
            mismatches.add(f"candidates.{field}", context, value, "<absent>")
        else:
            mismatches.compare(value, payload[field], f"candidates.{field}", context)
    actual = payload.get("candidates")
    if not isinstance(actual, list):
        mismatches.add("candidates.items", context, "array", actual)
        return
    wanted = selected[:500]
    mismatches.compare(len(wanted), len(actual), "candidates.length", context)
    by_key = {(row["title"], row["part"]): row for row in selected}
    global_rows = expected["candidates"]
    seen, ranks = set(), set()
    previous = None
    for index, row in enumerate(actual):
        if not isinstance(row, dict) or type(row.get("title")) is not int or type(row.get("part")) is not str:
            mismatches.add("candidates.identity", context, "integer title, string part", row)
            continue
        key = (row["title"], row["part"])
        location = f"{context} [{index}] {key}"
        reference = by_key.get(key)
        if key in seen or reference is None:
            mismatches.add("candidates.membership", location, "unique eligible part in set", key)
            continue
        seen.add(key)
        if index < len(wanted) and key != (wanted[index]["title"], wanted[index]["part"]):
            if not close(reference["score"], wanted[index]["score"]):
                mismatches.add("candidates.order", location, (wanted[index]["title"], wanted[index]["part"]), key)
        rank = row.get("rank")
        valid_rank = type(rank) is int and 1 <= rank <= len(global_rows)
        if not valid_rank or rank in ranks or not close(reference["score"], global_rows[rank - 1]["score"]):
            mismatches.add("candidates.rank", location, reference["rank"], rank)
        if valid_rank:
            ranks.add(rank)
            if previous is not None and rank <= previous:
                mismatches.add("candidates.rank_order", location, f"> {previous}", rank)
            previous = rank
        # Every candidate field except rank is exact/tolerant by its own type.
        mismatches.compare({k: v for k, v in reference.items() if k != "rank"},
                           {k: v for k, v in row.items() if k != "rank"}, "candidates", location)


def compare_base(base, expected, memberships):
    mismatches = Mismatches()
    payload = fetch(base, "/api/agencies", mismatches)
    if isinstance(payload, list):
        seen = set()
        for row in payload:
            slug = row.get("slug") if isinstance(row, dict) else None
            if not isinstance(slug, str) or slug not in expected["agencies"] or slug in seen:
                mismatches.add("agencies.slug", "/api/agencies", "unique known slug", slug)
                continue
            seen.add(slug)
            for field, value in expected["agencies"][slug].items():
                mismatches.compare(value, row.get(field), f"agencies.{field}", slug)
        for slug in sorted(expected["agencies"].keys() - seen):
            mismatches.add("agencies.missing", "/api/agencies", slug, "<absent>")
    elif payload is not FETCH_FAILED:
        mismatches.add("agencies.response", "/api/agencies", "array", payload)
    candidates = expected["candidates"]
    route = "/api/candidates?limit=500"
    payload = fetch(base, route, mismatches)
    if payload is not FETCH_FAILED:
        compare_candidates(payload, expected, candidates, "global", mismatches)
    checked = 0
    for slug, keys in sorted(memberships.items()):
        selected = [row for row in candidates if (row["title"], row["part"]) in keys]
        if not selected:
            continue
        route = "/api/candidates?" + urlencode({"agency": slug, "limit": 500})
        payload = fetch(base, route, mismatches)
        if payload is not FETCH_FAILED:
            compare_candidates(payload, expected, selected, slug, mismatches)
        checked += 1
        if checked % 25 == 0:
            print(f"Compared {checked} agency candidate routes", file=sys.stderr, flush=True)
    print(f"Checked agencies, global candidates, and {checked} agency candidate routes.")
    return mismatches.summary()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw/2026-10-29"))
    parser.add_argument("--snapshot", default="2026-10-29")
    parser.add_argument("--dump", type=Path)
    parser.add_argument("--base")
    args = parser.parse_args()
    if args.dump is None and args.base is None:
        parser.error("at least one of --dump or --base is required")
    started = time.perf_counter()
    expected, memberships = build_expected(args.raw, args.snapshot)
    computed = time.perf_counter() - started
    if args.dump is not None:
        with args.dump.open("w", encoding="utf-8") as destination:
            json.dump(expected, destination, ensure_ascii=False, allow_nan=False, indent=2)
            destination.write("\n")
        print(f"Wrote {args.dump}")
    print(f"Oracle compute: {computed:.3f}s; {len(expected['parts'])} parts; "
          f"{expected['eligible']} eligible; {expected['flagged']} flagged.")
    for row in expected["candidates"][:5]:
        print(f"  {row['rank']}. title {row['title']}, part {row['part']}: {row['score']:.15g}")
    failures = compare_base(args.base, expected, memberships) if args.base else 0
    print(f"Total runtime: {time.perf_counter() - started:.3f}s")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
