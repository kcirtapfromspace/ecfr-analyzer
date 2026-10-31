#!/bin/bash
# Warm-cache benchmark of H1/H2/H3. Run from the repo root after the raw cache is filled:
#   bench/bench.sh 2026-10-29 [--titles 1,40,41]
set -u
DATE=$1; shift
OUT=bench/results; mkdir -p "$OUT"
PY=(uv run python -I)
cmd() { if [ "$1" = h3 ]; then echo h3/target/release/ecfr; else echo "${PY[*]} $1/ecfr.py"; fi; }
port() { echo "830${1#h}"; }

pkill -f 'ecfr.py serve'; pkill -f 'release/ecfr serve'; sleep 0.5
for v in h1 h2 h3; do
  # shellcheck disable=SC2086
  /usr/bin/time -l $(cmd $v) ingest --date "$DATE" "$@" > "$OUT/ingest_$v.log" 2>&1 || { echo "$v ingest FAILED"; tail "$OUT/ingest_$v.log"; }
  wall=$(awk '/ real /{print $1}' "$OUT/ingest_$v.log"); rss=$(awk '/maximum resident/{printf "%.0f", $1/1048576}' "$OUT/ingest_$v.log")
  echo "$v ingest: ${wall}s wall, ${rss} MB max RSS, store $(du -sh data/$v | cut -f1)"
done

for v in h1 h2 h3; do
  # shellcheck disable=SC2086
  nohup $(cmd $v) serve --port "$(port $v)" > "$OUT/serve_$v.log" 2>&1 &
done
for v in h1 h2 h3; do until curl -s "localhost:$(port $v)/api/meta" > /dev/null; do sleep 0.3; done; done

"${PY[@]}" bench/parity.py 8301 8302 8303 | tee "$OUT/parity.txt"

for route in /api/agencies /api/agencies/environmental-protection-agency /api/agencies/environmental-protection-agency/history; do
  name=$(echo "$route" | tr '/' '_')
  hyperfine -N --warmup 5 --runs 100 --export-json "$OUT/lat$name.json" \
    -n h1 "curl -s -o /dev/null http://127.0.0.1:8301$route" \
    -n h2 "curl -s -o /dev/null http://127.0.0.1:8302$route" \
    -n h3 "curl -s -o /dev/null http://127.0.0.1:8303$route" > /dev/null
  "${PY[@]}" -c "import json,sys;d=json.load(open('$OUT/lat$name.json'));print('$route', ' '.join(f\"{r['name']}={r['summary']['time_wall_clock']['median']*1000:.1f}ms\" for r in d['results']))"
done

for v in h1 h2 h3; do
  pid=$(pgrep -f "serve --port $(port $v)" | head -1)
  echo "$v server RSS after load: $(( $(ps -o rss= -p "$pid") / 1024 )) MB"
done
