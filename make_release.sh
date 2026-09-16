#!/bin/sh
# Assemble the anonymous code-and-data release into ../checkable (a clean tree,
# not a git checkout of this repository). Run release_check.sh first.
#
#   sh make_release.sh            # builds ../checkable
#   cd ../checkable && git init && git add -A && git commit -m "Initial release"
#
# Then push to the private GitHub repository and mirror it through
# anonymous.4open.science; the paper cites the mirror.
set -e
DEST=${1:-../checkable}
# Keep the destination's .git (the pushed history the anonymous mirror points at); replace everything else.
mkdir -p "$DEST"
find "$DEST" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
mkdir -p "$DEST/data" "$DEST/paper" "$DEST/out"

# code
cp -r study tests paperengine "$DEST/"
find "$DEST" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
rm -f "$DEST/paperengine/litreview.py" "$DEST/paperengine/review.py" "$DEST/paperengine/sources.py" \
      "$DEST/paperengine/cli.py" "$DEST/paperengine/compliance.py" "$DEST/paperengine/repro.py" \
      "$DEST/paperengine/style.py" "$DEST/paperengine/refcheck.py"
cp run_all.sh requirements.txt "$DEST/"

# hand-judged audits (renderings, labels, scoring inputs); full paper texts are not shipped
cp -r audits "$DEST/audits"
find "$DEST/audits" -name "*_fulltext.txt" -delete
# the AAMAS study's kits belong to its own release, not this one
rm -rf "$DEST"/audits/aamas_* "$DEST/audits/gold_f/labels_gemini.json"
rm -rf "$DEST/audits/human/img" "$DEST/audits/human/README_VI.md" "$DEST"/audits/human/label*.html   # keep the CSVs and the English README

# extraction files: everything downstream regenerates from these two
cp data/extracted_2025.jsonl data/extracted_2024.jsonl "$DEST/data/"
cp data/corpus_manifest.json "$DEST/data/" 2>/dev/null || true
cp out/pipeline_stats_extracted_2025.json out/pipeline_stats_extracted_2024.json "$DEST/out/" 2>/dev/null || true

# the paper's macro file, so every number in the PDF can be matched to its source
mkdir -p "$DEST/paper/submission"
cp paper/submission/numbers.tex "$DEST/paper/submission/"

cp README_RELEASE.md "$DEST/README.md"
cp LICENSE "$DEST/LICENSE"

# nothing identifying may ship
if grep -r -n -i -E "thanh|nguyen|felice|tsinghua|talyxion|holy_grail" "$DEST" --include="*.py" --include="*.sh" --include="*.md" --include="*.csv" --include="*.json" --include="*.tex" -l | grep -v "audits/latex_source/cache.json"; then
  echo "identifying strings above: fix before pushing"; exit 1
fi
du -sh "$DEST"
echo "release tree at $DEST"
