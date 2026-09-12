#!/bin/sh
# What must be true of the tree before it is mirrored to the anonymous repository.
set -e
echo "-- files that must not ship"
ls data/*.bak out/*.bak 2>/dev/null && echo "   remove the .bak files above" || echo "   ok: no .bak files tracked (data/ and out/ are ignored anyway)"
echo "-- identifying strings in tracked files"
git grep -n -i -E "thanh|nguyen|felice|tsinghua|talyxion|holy_grail" -- . ':!release_check.sh' ':!paper/submission/refs.bib' && echo "   REMOVE the matches above" || echo "   ok: none"
echo "-- tests"
python -m pytest -q tests | tail -1
echo "-- gates"
./check.sh | tail -1
