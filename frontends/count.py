"""Count source lines the same way for every candidate: non-blank lines that are not pure comments."""

import pathlib
import re
import sys

COMMENT = re.compile(r"^\s*(//|#(?!\s*\{)|/\*|\*|<!--|-->)")
CANDIDATES = {
    "htmx": (["build.py", "templates/*.html", "static/*.js", "static/*.css"], ["package.json", "tsconfig.json", "globals.d.ts"]),
    "raw": (["public/index.html", "public/js/*.js", "public/style.css"], ["package.json", "tsconfig.json", "globals.d.ts"]),
    "sveltekit": (["src/**/*.svelte", "src/**/*.ts", "src/**/*.css", "src/app.html"], ["package.json", "tsconfig.json", "vite.config.ts"]),
    "sveltekit-lean": (["src/**/*.svelte", "src/**/*.ts", "src/**/*.css", "src/app.html"], ["package.json", "tsconfig.json", "vite.config.ts"]),
    "van": (["public/index.html", "public/js/*.js", "public/style.css"], ["package.json", "tsconfig.json", "globals.d.ts"]),
    "preact": (["public/index.html", "public/js/*.js", "public/style.css"], ["package.json", "tsconfig.json", "globals.d.ts"]),
    "observable": (["src/**/*.md", "src/components/*.js", "src/data/*.py"], ["package.json", "tsconfig.json", "observablehq.config.js"]),
}


def count(root, patterns, exclude=("test", ".test.", ".spec.")):
    files = sorted({p for pat in patterns for p in root.glob(pat) if p.is_file() and not any(x in str(p.relative_to(root)) for x in exclude)})
    lines = sum(1 for f in files for line in f.read_text().splitlines() if line.strip() and not COMMENT.match(line))
    return lines, [str(f.relative_to(root)) for f in files]


for name in sys.argv[1:] or CANDIDATES:
    src, cfg = CANDIDATES[name]
    root = pathlib.Path(name)
    code, files = count(root, src)
    config, _ = count(root, cfg, exclude=())
    tests, tfiles = count(root, ["test/*.js", "src/**/*.test.ts", "src/**/*.spec.ts"], exclude=())
    print(f"{name:10} code {code:4}  config {config:3}  unit tests {tests:3}  files {len(files)}: {', '.join(files)}")
