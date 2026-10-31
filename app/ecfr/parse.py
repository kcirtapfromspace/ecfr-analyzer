"""Stream one eCFR title's XML into a row per PART: structure, text hash, authority and sentence metrics."""

import gzip
import hashlib
import xml.etree.ElementTree as ET

from .text import RESTRICTION, WORD, authority, normalize, readability

ANCESTORS = {"SUBTITLE": "subtitle", "CHAPTER": "chapter", "SUBCHAP": "subchapter"}


def prose(el):
    """Text pieces of el in document order, skipping tables and equations (their tail text is kept)."""
    if el.tag in ("TABLE", "MATH"):
        return
    if el.text:
        yield el.text
    for child in el:
        yield from prose(child)
        if child.tail:
            yield child.tail


def parse_parts(path, title, known):
    """Stream one title's XML and yield (part row, text) per PART. Sentence metrics, the slow step, are
    reused from `known` ({(part, prose hash): counts}) when a part's prose is unchanged."""
    stack, ord_ = [], 0  # (TYPE, N) of every open element
    with gzip.open(path) as f:
        for event, el in ET.iterparse(f, events=("start", "end")):
            if event == "start":
                stack.append((el.get("TYPE"), el.get("N")))
                continue
            stack.pop()
            if el.get("TYPE") != "PART":
                continue
            ancestors = {ANCESTORS[t]: n for t, n in stack if t in ANCESTORS}  # innermost wins
            head = el.find("HEAD")
            text = normalize(" ".join(el.itertext()))
            auth = " ".join(normalize(" ".join(a.itertext())) for a in el.iter("AUTH"))
            tag, cites = authority(auth)
            prose_text = normalize(" ".join(prose(el)))
            prose_hash = hashlib.sha256(prose_text.encode()).hexdigest()
            row = (
                title,
                el.get("N"),
                ord_,
                ancestors.get("subtitle"),
                ancestors.get("chapter"),
                ancestors.get("subchapter"),
                normalize(" ".join(head.itertext())) if head is not None else "",
                len(WORD.findall(text)),
                len(RESTRICTION.findall(text.lower())),
                hashlib.sha256(text.encode()).hexdigest(),
                tag,
                cites,
                prose_hash,
                *(known.get((el.get("N"), prose_hash)) or readability(prose_text)),
            )
            yield row, text
            ord_ += 1
            el.clear()  # collect first, then free
