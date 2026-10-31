"""Definitions and helpers shared by ingest and web."""

import json
import os

CUTOFF = "2017-01-01"  # earlier version rows are the eCFR baseline load, not changes
INPUTS = ("size", "density", "grade", "directive", "paperwork", "staleness")


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)
