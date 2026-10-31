"""Definitions and helpers shared by ingest and web."""

import json
import os

CUTOFF = "2017-01-01"  # earlier version rows are the eCFR baseline load, not changes
# The six ranking inputs, in order, with the name and definition that every page shows for them.
INPUTS = {
    "size": ("Size", "Words in the part (log scale)"),
    "density": ("Restriction density", "Restriction terms (shall, must, may not ...) per 1k words"),
    "grade": ("Reading grade", "Approximate Flesch-Kincaid grade of the prose"),
    "directive": ("Directive share", "Share of obligation, prohibition and paperwork sentences"),
    "paperwork": ("Paperwork share", "Share of sentences about reports, records and forms"),
    "staleness": ("Unchanged since 2017", "Share of sections with no recorded change since 2017"),
}


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)
