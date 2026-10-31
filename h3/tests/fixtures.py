#!/usr/bin/env python3
"""Exercise full ingest on tiny caches, including refresh and failure atomicity."""

import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile

from verify import compare_store, oracle


def agency(slug, refs, children=None, short_name=None):
    return dict(slug=slug, name=slug.title(), short_name=short_name,
                cfr_references=refs, children=children or [])


def write_json(path, value):
    path.write_text(json.dumps(value))


def main():
    binary = Path("h3/target/release/ecfr").resolve()
    date = "2026-10-29"
    with tempfile.TemporaryDirectory(prefix="ecfr-h3-fixtures-") as temporary:
        root = Path(temporary)
        cache = root / "data" / "raw" / date
        cache.mkdir(parents=True)
        child = agency("child", [dict(title=1, chapter="0")], short_name="")
        child.pop("children")
        sources = [
            agency("parent", [dict(title=1, chapter="0", part="z")], [child]),
            agency("subtitle", [dict(title=1, subtitle="A")]),
            agency("subchapter", [dict(title=1, chapter="0", subchapter="B")]),
            agency("both", [dict(title=1, subtitle="A", chapter="0")]),
            agency("empty", [dict(title=2, chapter="I")]),
        ]
        write_json(cache / "agencies.json", dict(agencies=sources))
        title_metadata = dict(titles=[dict(number=1, reserved=False)], meta=dict(import_in_progress=False, date=date))
        write_json(cache / "titles.json", title_metadata)
        xml = """<ECFR><DIV1 TYPE="TITLE" N="1"><DIV2 TYPE="SUBTITLE" N="A">
        <DIV3 TYPE="CHAPTER" N="0"><DIV4 TYPE="SUBCHAP" N="B">
        <AUTH>99 U.S.C. 1</AUTH>
        <DIV5 TYPE="PART" N="z"><HEAD>Part z — Cafe&#x301;</HEAD>
        <P>Alpha<I>shall</I> tail &amp; z<![CDATA[ero]]> 12_34.</P>
        <DIV8 TYPE="SECTION" N="z.1"><HEAD>Nested heading</HEAD><P>must required may not prohibited</P></DIV8>
        <AUTH>5 <I>U.S.C.</I> 301; 42 U.S.C. 123a</AUTH>
        <DIV6 TYPE="SUBPART"><AUTH>42 U.S.C. 123a; Pub. L. 1</AUTH></DIV6>
        </DIV5><DIV5 TYPE="PART" N="a"><P>Beta shall.<!-- excluded -->Tail</P></DIV5>
        <DIV5 TYPE="PART" N="hk"><AUTH>5 U.S.C. 301, 552; Executive Order 1; public law</AUTH></DIV5>
        <DIV5 TYPE="PART" N="ex"><AUTH>E. O. 7</AUTH></DIV5>
        <DIV5 TYPE="PART" N="other"><AUTH>18 U.S.C. appendix; public law</AUTH></DIV5>
        <DIV5 TYPE="PART" N="pub"><AUTH>Public Law 1; Executive Order 2</AUTH></DIV5>
        <DIV5 TYPE="PART" N="tie2"><AUTH>2 U.S.C. 3</AUTH></DIV5>
        <DIV5 TYPE="PART" N="tie10"><AUTH>10 U.S.C. 3</AUTH></DIV5>
        <DIV5 TYPE="PART" N="blank"><AUTH> 
 </AUTH><P>Blank</P></DIV5>
        </DIV4></DIV3></DIV2></DIV1></ECFR>"""
        xml_path = cache / "title-1.xml.gz"
        xml_path.write_bytes(gzip.compress(xml.encode()))
        rows = []
        for identifier, event_date, part, substantive, removed in [
            ("base", "2016-12-31", "z", False, False),
            ("base", "2016-12-31", "z", True, False),
            ("start", "2017-01-01", "z", False, False),
            ("start", "2017-01-01", "z", True, False),
            ("removed", "2018-01-01", "a", True, False),
            ("removed", "2018-01-01", "a", False, True),
            ("orphan", "2019-01-01", None, True, False),
            ("orphan", "2019-01-01", None, False, True),
            ("non", "2020-01-01", "z", False, False),
            ("missing", "2026-10-29", "missing", True, False),
            ("future", "2026-10-30", "z", True, False),
            ("base", "2020-01-01", "z", False, True),
            ("revive", "2016-12-31", "a", True, False),
            ("revive", "2019-01-01", "a", False, True),
            ("revive", "2021-01-01", "a", False, False),
            ("old", "2016-12-31", "a", True, False),
            ("old", "2027-01-01", "a", False, True),
            ("same-id", "2016-12-31", "z", True, False),
            ("same-id", "2016-12-31", "a", True, False),
            ("remove-old", "2016-12-31", "a", False, True),
            ("dup-removed", "2016-12-31", "z", False, False),
            ("dup-removed", "2016-12-31", "z", True, True),
        ]:
            rows.append(dict(title="999", type="section", identifier=identifier,
                             date=event_date, part=part, substantive=substantive, removed=removed))
        rows.append(dict(title="999", type="appendix", identifier="same-id",
                         date="2016-12-31", part="z", substantive=True, removed=False))
        versions = dict(result_count=len(rows), content_versions=rows)
        write_json(cache / "versions-1.json", versions)
        store = root / "data" / "h3" / "ecfr.sqlite"

        def ingest(success=True):
            result = subprocess.run([str(binary), "ingest", "--date", date, "--titles", "1"], cwd=root, capture_output=True, text=True)
            assert (result.returncode == 0) == success, (result.returncode, result.stdout, result.stderr)

        before = {path.name: path.read_bytes() for path in cache.iterdir()}
        ingest()
        parts, responses, _ = oracle(cache, [1], date)
        compare_store(store, parts, responses)
        assert all(path.read_bytes() == before[path.name] for path in cache.iterdir()), "cache hit rewrote bytes"
        meta = responses["/api/meta"]
        parent = responses["/api/agencies/parent"]
        assert meta["baseline_rows"] == 8
        assert meta["change_rows"] == 8
        assert meta["unmatched_events"] == 2
        assert parent["parts"] == 9
        assert parent["top_parts"][0]["heading"] == "Part z — Café"
        expected_tags = dict(z="statute", a="none", hk="housekeeping", ex="executive",
                             other="other", pub="statute", tie2="statute", tie10="statute", blank="none")
        assert {part["part"]: part["authority"] for part in parent["top_parts"]} == expected_tags
        assert meta["authority_words"] == parent["authority_words"] == dict(
            statute=50, housekeeping=11, executive=3, other=7, none=4)
        assert parent["top_statutes"] == [
            dict(cite="5 U.S.C. 301", parts=2, words=45),
            dict(cite="42 U.S.C. 123a", parts=1, words=34),
            dict(cite="10 U.S.C. 3", parts=1, words=5),
            dict(cite="2 U.S.C. 3", parts=1, words=5),
        ]
        assert (meta["sections"], meta["stale_sections"]) == (7, 4)
        assert (parent["sections"], parent["stale_sections"], parent["stale_share"]) == (7, 4, 4 / 7)
        empty = responses["/api/agencies/empty"]
        assert (empty["sections"], empty["stale_sections"], empty["stale_share"], empty["top_statutes"]) == (0, 0, None, [])
        assert empty["authority_words"] == dict(statute=0, housekeeping=0, executive=0, other=0, none=0)
        previous = {agency["slug"]: agency["checksum"] for agency in responses["/api/agencies"]}
        ingest()
        compare_store(store, parts, responses)
        xml_path.write_bytes(gzip.compress(xml.replace("Alpha", "Alpha!").encode()))
        sources[-1]["cfr_references"] = [dict(title=1, chapter="0", part="a")]
        write_json(cache / "agencies.json", dict(agencies=sources))
        ingest()
        changed_parts, changed_responses, _ = oracle(cache, [1], date, previous=previous)
        compare_store(store, changed_parts, changed_responses)
        assert changed_responses["/api/agencies/parent"]["changed"] is True
        assert changed_responses["/api/agencies/empty"]["changed"] is False
        assert changed_responses["/api/agencies/empty"]["checksum"] is not None
        previous = {agency["slug"]: agency["checksum"] for agency in changed_responses["/api/agencies"]}
        sources[-1]["cfr_references"] = [dict(title=2, chapter="I")]
        write_json(cache / "agencies.json", dict(agencies=sources))
        ingest()
        changed_parts, changed_responses, _ = oracle(cache, [1], date, previous=previous)
        compare_store(store, changed_parts, changed_responses)
        assert changed_responses["/api/agencies/parent"]["changed"] is False
        assert changed_responses["/api/agencies/empty"]["changed"] is True
        assert changed_responses["/api/agencies/empty"]["checksum"] is None

        checksum = hashlib.sha256(store.read_bytes()).digest()
        title_metadata["meta"]["import_in_progress"] = True
        write_json(cache / "titles.json", title_metadata)
        ingest(False)
        assert hashlib.sha256(store.read_bytes()).digest() == checksum, "failed metadata refresh replaced old store"
        title_metadata["meta"]["import_in_progress"] = False
        write_json(cache / "titles.json", title_metadata)
        versions["result_count"] += 1
        write_json(cache / "versions-1.json", versions)
        ingest(False)
        assert hashlib.sha256(store.read_bytes()).digest() == checksum, "failed history refresh replaced old store"
        versions["result_count"] -= 1
        write_json(cache / "versions-1.json", versions)
        xml_path.write_bytes(b"invalid gzip")
        ingest(False)
        assert hashlib.sha256(store.read_bytes()).digest() == checksum, "failed XML refresh replaced old store"
        with sqlite3.connect(store) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        print("Fixture verification passed: five reference shapes, chapter 0, parent union, normalization, authority tags/cites/precedence/statute ordering, history de-duplication/OR/cutoff/null keys, section staleness/removal/reintroduction/type keys, unmatched events, refresh changes/null transitions, cache hits and failed-ingest preservation.")


if __name__ == "__main__":
    main()
