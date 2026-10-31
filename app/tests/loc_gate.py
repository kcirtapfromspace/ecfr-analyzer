"""Fail when the app's code exceeds the 1,200-line budget.

Counted exactly as every report in RESULTS.md counts it: `tokei app --exclude tests` (tokei 15.0.0),
code lines only, so blank lines, comments and the tests themselves don't count.
"""

import json
import subprocess
import sys

LIMIT = 1200

out = subprocess.run(["tokei", "app", "--exclude", "tests", "-o", "json"], check=True, capture_output=True, text=True)
report = json.loads(out.stdout)
for language, stats in sorted(report.items()):
    if language != "Total" and stats["code"]:
        print(f"{language:12} {stats['code']:5}")
total = report["Total"]["code"]
print(f"{'total':12} {total:5} / {LIMIT}")
sys.exit(0 if total <= LIMIT else f"over the {LIMIT}-line budget by {total - LIMIT} lines")
