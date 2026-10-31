"""Text metrics on normalized strings: words, restriction terms, authority tags, sentences, readability."""

import re
import unicodedata

WORD = re.compile(r"[^\W_]+")
RESTRICTION = re.compile(r"\b(shall|must|may not|required|prohibited)\b")
USC = re.compile(r"(\d+)\s*U\.\s*S\.\s*C\.?\s+(\d+[A-Za-z]*)")
PUBLAW = re.compile(r"Pub\.\s*L\.|Public Law")
EXECUTIVE = re.compile(r"E\.\s*O\.|Executive Order|Proclamation|Reorganization Plan")
TAGS = ("statute", "housekeeping", "executive", "other", "none")

# Sentence structure (CONTRACT.md, Round 3). Approximate by design: legal text defeats simple splitters.
BOUNDARY = re.compile(r'(?<=[.?!])\s+(?=[A-Z(§"“])')
ABBREVIATION = re.compile(
    r"(?:^|[\s(])(?:U\.S\.C|U\.S|e\.g|i\.e|etc|et seq|No|Nos|Sec|Secs|Pub|L|Stat|Fed|Reg|Inc|Co|Corp"
    r"|Ltd|Dr|Mr|Mrs|Ms|St|Jr|Vol|Ch|Pt|App|cf|al|approx|ft|in|lb|lbs|oz|Jan|Feb|Mar|Apr|Jun|Jul"
    r"|Aug|Sep|Sept|Oct|Nov|Dec|[A-Z])\.$"
)
VOWELS = re.compile(r"[aeiouy]+")
NO_VOWEL_WORD = re.compile(r"(?<![^\W_])[^\W_aeiouy]+(?![^\W_])")  # whole words with no vowel run
PASSIVE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?\w+(?:ed|en)\b")
CROSSREF = re.compile(
    r"§|\bparagraphs? \(|\bsections? \d|\bparts? \d|\bsubparts? [a-z]\b|u\.s\.c\."
)
DEFINITION = re.compile(
    r"\b(?:means|is defined as|has the meaning|have the meaning|as used in this)\b"
)
PROHIBITION = re.compile(
    r"\b(?:shall not|must not|may not|is prohibited|are prohibited|prohibited from"
    r"|no person shall|no person may)\b"
)
DUTY = re.compile(r"\b(?:shall|must|is required to|are required to)\b")
FILING = re.compile(
    r"\b(?:report|reports|record|records|recordkeeping|submit|submits|submitted|notify|notification"
    r"|certify|certification|application|apply|file|filing|disclose|disclosure|form|forms)\b"
)
OBLIGATION = re.compile(r"\b(?:shall|must|is required to|are required to|required)\b")
PERMISSION = re.compile(r"\bmay\b")
TYPES = ("definition", "prohibition", "paperwork", "obligation", "permission", "other")
SUMMED = (
    "prose_words",
    "sentences",
    "long_sentences",
    "syllables",
    "passive_sentences",
    "crossrefs",
)
SUMMED += TYPES


def normalize(text):
    return " ".join(unicodedata.normalize("NFC", text).split())


def authority(text):
    """Tag what a part's authority note cites (see CONTRACT.md). Descriptive, not a legal conclusion."""
    cites = sorted({f"{t} U.S.C. {s}" for t, s in USC.findall(text)})
    if not text:
        return "none", cites
    if set(cites) - {"5 U.S.C. 301"} or PUBLAW.search(text):
        return "statute", cites
    if cites:
        return "housekeeping", cites  # only the general Housekeeping Statute
    return ("executive" if EXECUTIVE.search(text) else "other"), cites


def sentences(text):
    kept = []
    for piece in BOUNDARY.split(text):
        if kept and ABBREVIATION.search(kept[-1]):
            kept[-1] += " " + piece  # "U.S.C. 301" or "e.g. Part" is not a sentence break
        else:
            kept.append(piece)
    return [s for s in kept if WORD.search(s)]


def classify(sentence):
    """Typed decision per sentence; the first matching rule wins (CONTRACT.md)."""
    s = sentence.lower()
    if DEFINITION.search(s):
        return "definition"
    if PROHIBITION.search(s):
        return "prohibition"
    if DUTY.search(s) and FILING.search(s):
        return "paperwork"
    if OBLIGATION.search(s):
        return "obligation"
    return "permission" if PERMISSION.search(s) else "other"


def readability(text):
    """(prose_words, sentences, long_sentences, syllables, passive_sentences, crossrefs, *TYPES counts)."""
    lower = text.lower()
    found = sentences(text)
    types = dict.fromkeys(TYPES, 0)
    long_sentences = passive = 0
    for s in found:
        types[classify(s)] += 1
        long_sentences += len(WORD.findall(s)) > 40
        passive += bool(PASSIVE.search(s.lower()))
    # Σ max(1, vowel runs) per word = all vowel runs + one for each word that has none.
    syllables = len(VOWELS.findall(lower)) + len(NO_VOWEL_WORD.findall(lower))
    counts = (len(WORD.findall(text)), len(found), long_sentences, syllables, passive)
    return (*counts, len(CROSSREF.findall(lower)), *types.values())
