#!/usr/bin/env bash
# The demo profile, start to finish, without a browser. Writes examples/walkthrough.txt.
set -euo pipefail
cd "$(dirname "$0")/.."
work=$(mktemp -d)
out=examples/walkthrough.txt
bw() { echo "\$ bw $*" | sed "s#$work#<work>#g"; python3 -m bookmarkwise "$@" 2>&1 | sed "s#$work#<work>#g; s#$(pwd)/##g" || true; echo; }
{
  bw inventory --bookmarks examples/demo/Bookmarks --out "$work/inventory.json"
  bw freeze examples/demo-draft.json --bookmarks examples/demo/Bookmarks --out "$work/plan.json"
  bw show "$work/plan.json"
  bw build "$work/plan.json" --out "$work/extension"
  bw approve "$work/plan.json"
  bw check "$work/plan.json" --bookmarks examples/demo/Bookmarks
  bw build "$work/plan.json" --out "$work/extension"
} > "$out"
rm -rf "$work"
echo "wrote $out"
