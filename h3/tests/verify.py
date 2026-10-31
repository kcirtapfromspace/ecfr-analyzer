#!/usr/bin/env python3
"""Independent stdlib oracle for every H3 part and API response."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from urllib.request import urlopen
import xml.etree.ElementTree as ET


def normalized(element):
    if element is None:
        return ""
    return " ".join(unicodedata.normalize("NFC", " ".join(element.itertext())).split())


AUTHORITY_TAGS = ("statute", "housekeeping", "executive", "other", "none")


def authority_fields(element):
    text = " ".join(normalized(note) for note in element.iter("AUTH"))
    cites = sorted({f"{title} U.S.C. {section}" for title, section in re.findall(
        r"(\d+)\s*U\.\s*S\.\s*C\.?\s+(\d+[A-Za-z]*)", text)})
    if text == "":
        tag = "none"
    elif set(cites) - {"5 U.S.C. 301"} or re.search(r"Pub\.\s*L\.|Public Law", text):
        tag = "statute"
    elif cites:
        tag = "housekeeping"
    elif re.search(r"E\.\s*O\.|Executive Order|Proclamation|Reorganization Plan", text):
        tag = "executive"
    else:
        tag = "other"
    return dict(authority=tag, cites=cites)


def authority_words(parts):
    totals = dict.fromkeys(AUTHORITY_TAGS, 0)
    for part in parts:
        totals[part["authority"]] += part["words"]
    return totals


def load_parts(cache, titles):
    parts = {}
    boundary_differences = []
    for title in titles:
        stack = []
        active = 0
        ordinal = 0
        with gzip.open(cache / f"title-{title}.xml.gz", "rb") as source:
            for event, element in ET.iterparse(source, events=("start", "end")):
                if event == "start":
                    stack.append(element)
                    if element.get("TYPE") == "PART":
                        active += 1
                    continue
                if element.get("TYPE") == "PART":
                    text = normalized(element)
                    record = {"title": title, "part": element.get("N"), "ord": ordinal}
                    for key, kind in [("subtitle", "SUBTITLE"), ("chapter", "CHAPTER"), ("subchapter", "SUBCHAP")]:
                        record[key] = next((el.get("N") for el in reversed(stack[:-1]) if el.get("TYPE") == kind), None)
                    lower = text.lower()
                    record.update(
                        heading=normalized(element.find("HEAD")),
                        words=len(re.findall(r"[^\W_]+", text)),
                        restrictions=len(re.findall(r"\b(shall|must|may not|required|prohibited)\b", lower)),
                        hash=hashlib.sha256(text.encode()).hexdigest(),
                    )
                    record.update(authority_fields(element))
                    # Rust's Unicode \b additionally treats combining marks as word characters.
                    for match in re.finditer(r"\b(shall|must|may not|required|prohibited)\b", lower):
                        neighbors = lower[max(0, match.start() - 1):match.start()] + lower[match.end():match.end() + 1]
                        if any(unicodedata.category(ch).startswith("M") or ch in "\u200c\u200d" for ch in neighbors):
                            boundary_differences.append((title, record["part"], match.group(), neighbors))
                    key = title, record["part"]
                    assert key not in parts, ("duplicate part", key)
                    parts[key] = record
                    ordinal += 1
                    active -= 1
                stack.pop()
                if not active:
                    element.clear()
    return parts, boundary_differences


def oracle(cache, titles, date, previous=None):
    parts, boundary_differences = load_parts(cache, titles)
    agencies = {}
    for parent in json.loads((cache / "agencies.json").read_text())["agencies"]:
        for source, parent_slug in [(parent, None)] + [(child, parent["slug"]) for child in parent["children"]]:
            agency = {key: source[key] for key in ["slug", "name", "short_name"]}
            agency.update(parent_slug=parent_slug, refs=source["cfr_references"], children=[child["slug"] for child in source.get("children", [])])
            agency["own"] = {
                key for key, part in parts.items()
                if any(all(part[field] == ref[field] for field in ["title", "subtitle", "chapter", "subchapter", "part"] if field in ref) for ref in agency["refs"])
            }
            agencies[agency["slug"]] = agency
    versions = {}
    for title in titles:
        history = json.loads((cache / f"versions-{title}.json").read_text())
        assert len(history["content_versions"]) == history["result_count"]
        for source in history["content_versions"]:
            if source["date"] > date:
                continue
            # Contract revision: part is in the key (an appendix can be listed under several parts);
            # a null part equals a null part, as in SQL GROUP BY.
            key = (title, source["part"], source["type"], source["identifier"], source["date"])
            row = versions.setdefault(key, dict(source, title=title, substantive=False, removed=False))
            row["substantive"] |= source["substantive"]
            row["removed"] |= source["removed"]
    latest = {}
    for key, row in versions.items():
        section_key = key[:-1]
        if section_key not in latest or row["date"] > latest[section_key]["date"]:
            latest[section_key] = row
    # "Section" includes every type in the versions data; the contract's key includes type.
    current_by_part = {}
    for row in latest.values():
        part_key = row["title"], row["part"]
        if not row["removed"] and part_key in parts:
            counts = current_by_part.setdefault(part_key, [0, 0])
            counts[0] += 1
            counts[1] += row["date"] < "2017-01-01"
    attributed = set().union(*(agency["own"] for agency in agencies.values()))
    responses = {"/api/meta": {
        "ecfr_date": date, "titles": titles, "parts": len(parts),
        "words": sum(part["words"] for part in parts.values()),
        "unattributed_words": sum(part["words"] for key, part in parts.items() if key not in attributed),
        "baseline_rows": sum(row["date"] < "2017-01-01" for row in versions.values()),
        "change_rows": sum(row["date"] >= "2017-01-01" for row in versions.values()),
        "unmatched_events": sum(row["date"] >= "2017-01-01" and (row["title"], row["part"]) not in parts for row in versions.values()),
        "authority_words": authority_words(parts.values()),
        "sections": sum(counts[0] for counts in current_by_part.values()),
        "stale_sections": sum(counts[1] for counts in current_by_part.values()),
    }}
    summaries = []
    for slug, agency in agencies.items():
        members = agency["own"].union(*(agencies[child]["own"] for child in agency["children"]))
        ordered = sorted((parts[key] for key in members), key=lambda part: (part["title"], part["ord"]))
        words = sum(part["words"] for part in ordered)
        restrictions = sum(part["restrictions"] for part in ordered)
        checksum = hashlib.sha256("".join(f'{part["title"]}|{part["part"]}|{part["hash"]}\n' for part in ordered).encode()).hexdigest() if members else None
        rows = [row for row in versions.values() if (row["title"], row["part"]) in members]
        sections = sum(current_by_part.get(key, [0, 0])[0] for key in members)
        stale_sections = sum(current_by_part.get(key, [0, 0])[1] for key in members)
        summary = {key: agency[key] for key in ["slug", "name", "short_name", "parent_slug"]}
        summary.update(words=words, restrictions=restrictions, density=1000.0 * restrictions / words if words else None, parts=len(members), checksum=checksum,
                       changed=bool(previous and previous.get(slug) is not None and previous[slug] != checksum), last_changed=max((row["date"] for row in rows), default=None))
        summary.update(authority_words=authority_words(ordered), sections=sections,
                       stale_sections=stale_sections, stale_share=stale_sections / sections if sections else None)
        summaries.append(summary)
        top_parts = sorted(ordered, key=lambda part: (-part["words"], part["title"], part["ord"]))[:10]
        statutes = {}
        for part in ordered:
            for cite in part["cites"]:
                counts = statutes.setdefault(cite, dict(cite=cite, parts=0, words=0))
                counts["parts"] += 1
                counts["words"] += part["words"]
        top_statutes = sorted(statutes.values(), key=lambda statute: (-statute["words"], statute["cite"]))[:10]
        responses[f"/api/agencies/{slug}"] = dict(summary, refs=agency["refs"], children=agency["children"],
            top_parts=[{key: part[key] for key in ["title", "part", "heading", "words", "restrictions", "authority"]} for part in top_parts],
            top_statutes=top_statutes)
        years = {}
        for row in rows:
            if row["date"] < "2017-01-01":
                continue
            year = int(row["date"][:4])
            counts = years.setdefault(year, dict(year=year, substantive=0, nonsubstantive=0, removed=0))
            counts["removed" if row["removed"] else "substantive" if row["substantive"] else "nonsubstantive"] += 1
        responses[f"/api/agencies/{slug}/history"] = dict(slug=slug, years=[years[year] for year in sorted(years)])
    responses["/api/agencies"] = sorted(summaries, key=lambda agency: (-agency["words"], agency["slug"]))
    return parts, responses, boundary_differences


def compare_store(store, parts, responses):
    with sqlite3.connect(store) as connection:
        connection.row_factory = sqlite3.Row
        actual_parts = {}
        for row in connection.execute("SELECT title,part,subtitle,chapter,subchapter,heading,ord,words,restrictions,hash,authority,cites_json FROM part"):
            record = dict(row)
            record["cites"] = json.loads(record.pop("cites_json"))
            actual_parts[row["title"], row["part"]] = record
        assert actual_parts == parts, ("parts differ", next((key for key in parts if actual_parts.get(key) != parts[key]), None))
        actual_responses = {row["path"]: json.loads(row["body"]) for row in connection.execute("SELECT path,body FROM response")}
    assert set(actual_responses) == set(responses), "response route set differs"
    actual_responses["/api/meta"].pop("ingested_at")
    for path, expected in responses.items():
        assert actual_responses[path] == expected, (path, actual_responses[path], expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("data/raw/2026-10-29"))
    parser.add_argument("--titles", default="1,40,41")
    parser.add_argument("--date", default="2026-10-29")
    parser.add_argument("--store", type=Path, default=Path("data/h3/ecfr.sqlite"))
    parser.add_argument("--base")
    args = parser.parse_args()
    parts, responses, boundary_differences = oracle(args.cache, sorted(map(int, args.titles.split(","))), args.date)
    compare_store(args.store, parts, responses)
    if args.base:
        for path, expected in responses.items():
            with urlopen(args.base + path) as response:
                actual = json.load(response)
            if path == "/api/meta":
                actual.pop("ingested_at")
            assert actual == expected, path
    before = Path(__file__).with_name("cache-before.json")
    if before.exists() and args.cache == Path("data/raw/2026-10-29"):
        for name, expected in json.loads(before.read_text()).items():
            assert hashlib.sha256((args.cache / name).read_bytes()).hexdigest() == expected, ("raw cache changed", name)
    print(f"Verified {len(parts)} parts and {len(responses)} API responses against independent Python oracle.")
    print("Meta:", json.dumps(responses["/api/meta"], sort_keys=True))
    print("Restriction boundary differences:", boundary_differences)


if __name__ == "__main__":
    main()
