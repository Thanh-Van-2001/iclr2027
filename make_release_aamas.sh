#!/bin/sh
# Assemble the anonymous release of the AAMAS paper into ../checkable-aamas:
# the frozen instrument (study/), the AAMAS-specific scripts (aamas/), the
# extraction file, the audits with their renderings and labels, and every run
# record the paper's numbers come from.
set -e
DEST=${1:-../checkable-aamas}
mkdir -p "$DEST"
find "$DEST" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
mkdir -p "$DEST/data" "$DEST/out/aamas" "$DEST/paper/aamas" "$DEST/audits"

cp -r study aamas paperengine "$DEST/"
find "$DEST" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
rm -f "$DEST/paperengine/litreview.py" "$DEST/paperengine/review.py" "$DEST/paperengine/sources.py" \
      "$DEST/paperengine/cli.py" "$DEST/paperengine/compliance.py" "$DEST/paperengine/repro.py" \
      "$DEST/paperengine/style.py" "$DEST/paperengine/refcheck.py"
rm -f "$DEST/aamas/make_reader_wf.py" "$DEST/aamas/stub_check.py"
cp run_all_aamas.sh requirements.txt "$DEST/"

cp -r audits/aamas_gold audits/aamas_gold_gemini audits/aamas_pages "$DEST/audits/"
# the census kits ship their items, labels and draw records; the page images
# (hundreds of MB) are regenerated from data/corpus by the sampling scripts
for kit in aamas_census aamas_census_retry aamas_census_effort aamas_census_zero aamas_noncaption aamas_testable_pages; do
  mkdir -p "$DEST/audits/$kit"
  cp audits/$kit/*.json "$DEST/audits/$kit/"
done
# the mainstream random pages of the concurrent study, with both readers' labels
# (renders in that study's release; study/sample_pages.py regenerates them)
mkdir -p "$DEST/audits/gold_f"
cp audits/gold_f/items.json audits/gold_f/labels.json audits/gold_f/labels_gemini.json audits/gold_f/labels_geminir.json audits/gold_f/labels_gemini_merged.json "$DEST/audits/gold_f/" 2>/dev/null || true
cp out/gold_set_pages.json out/analysis_2025.json "$DEST/out/" 2>/dev/null || true
find "$DEST/audits" -name "*_fulltext.txt" -delete
cp data/extracted_aamas.jsonl "$DEST/data/"
# the NeurIPS/ICML side-by-side is read from these two records
cp out/both_years.json out/extra_stats.json "$DEST/out/"
cp out/aamas/*.json out/aamas/communities.csv "$DEST/out/aamas/"
cp -r audits/aamas_comm_check "$DEST/audits/"
cp paper/aamas/numbers.tex "$DEST/paper/aamas/"
cp README_RELEASE_AAMAS.md "$DEST/README.md"
cp LICENSE "$DEST/LICENSE"

# ("Nguyen et al." inside a source paper's caption text is a cited author, not an identity)
if grep -r -n -i -E "thanh|nguyen|felice|tsinghua|talyxion|holy_grail|beetrade|sk-b80" "$DEST" --include="*.py" --include="*.sh" --include="*.md" --include="*.csv" --include="*.json" --include="*.tex" | grep -v -i "nguyen et al" | cut -d: -f1 | sort -u | grep .; then
  echo "identifying strings above: fix before pushing"; exit 1
fi
du -sh "$DEST"
echo "release tree at $DEST"
