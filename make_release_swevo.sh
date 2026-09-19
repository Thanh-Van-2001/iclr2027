#!/bin/sh
# Assemble the release of the metaheuristics paper into ../checkable-metaheuristics:
# the frozen instrument (study/), the study-specific scripts (swevo/), the
# extraction file, the audits with their labels, and every run record the
# paper's numbers come from.
set -e
DEST=${1:-../checkable-metaheuristics}
mkdir -p "$DEST"
find "$DEST" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
mkdir -p "$DEST/data" "$DEST/out/swevo" "$DEST/paper/swevo" "$DEST/audits"

cp -r study swevo paperengine "$DEST/"
# the AAMAS classifier's relay call is imported by swevo/classify.py and swevo/test_reader.py
mkdir -p "$DEST/aamas"
cp aamas/classify.py aamas/make_all_aamas.py aamas/rate_labels.py aamas/__init__.py "$DEST/aamas/" 2>/dev/null || true
find "$DEST" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
rm -f "$DEST/paperengine/litreview.py" "$DEST/paperengine/review.py" "$DEST/paperengine/sources.py" \
      "$DEST/paperengine/cli.py" "$DEST/paperengine/compliance.py" "$DEST/paperengine/repro.py" \
      "$DEST/paperengine/style.py" "$DEST/paperengine/refcheck.py"
cp run_all_swevo.sh requirements.txt "$DEST/"

mkdir -p "$DEST/audits/swevo_gold" "$DEST/audits/swevo_census"
cp audits/swevo_gold/items.json audits/swevo_gold/labels_template.csv "$DEST/audits/swevo_gold/"
cp audits/swevo_gold/labels*.csv "$DEST/audits/swevo_gold/" 2>/dev/null || true
cp -r audits/swevo_gold/img "$DEST/audits/swevo_gold/"
cp audits/swevo_census/*.json "$DEST/audits/swevo_census/"
mkdir -p "$DEST/audits/swevo_verdict" "$DEST/audits/swevo_human" "$DEST/audits/swevo_census_retry"
cp audits/swevo_verdict/*.json audits/swevo_verdict/*.txt "$DEST/audits/swevo_verdict/"
cp audits/swevo_census_retry/items.json "$DEST/audits/swevo_census_retry/"
# the human kit ships its items, template and labelling sheet; the page images are those of the census
cp audits/swevo_human/items.json audits/swevo_human/draw.json audits/swevo_human/labels_template.csv audits/swevo_human/label.html "$DEST/audits/swevo_human/"
cp audits/swevo_human/labels*.csv "$DEST/audits/swevo_human/" 2>/dev/null || true
mkdir -p "$DEST/audits/swevo_human_rows" "$DEST/audits/swevo_census_rows"
cp audits/swevo_human_rows/items.json audits/swevo_human_rows/draw.json audits/swevo_human_rows/labels_template.csv audits/swevo_human_rows/label.html "$DEST/audits/swevo_human_rows/"
cp audits/swevo_human_rows/labels*.csv "$DEST/audits/swevo_human_rows/" 2>/dev/null || true
cp audits/swevo_census_rows/*.json audits/swevo_census_rows/instruction.txt "$DEST/audits/swevo_census_rows/"
mkdir -p "$DEST/audits/swevo_census_cols"
cp audits/swevo_census_cols/*.json "$DEST/audits/swevo_census_cols/" 2>/dev/null || true
mkdir -p "$DEST/audits/swevo_markers"
cp audits/swevo_markers/*.csv "$DEST/audits/swevo_markers/" 2>/dev/null || true
mkdir -p "$DEST/audits/swevo_census_rows2"
cp audits/swevo_census_rows2/*.json audits/swevo_census_rows2/instruction.txt "$DEST/audits/swevo_census_rows2/"
mkdir -p "$DEST/audits/swevo_census_rows3"
cp audits/swevo_census_rows3/*.json audits/swevo_census_rows3/instruction.txt "$DEST/audits/swevo_census_rows3/"
cp audits/swevo_verdict/papers2.txt "$DEST/audits/swevo_verdict/" 2>/dev/null || true
cp paper/swevo/supplement.tex "$DEST/paper/swevo/" 2>/dev/null || true
find "$DEST/audits" -name "*_fulltext.txt" -delete
cp data/extracted_oa.jsonl "$DEST/data/"
cp data/extracted_pmc.jsonl "$DEST/data/" 2>/dev/null || true
cp out/pipeline_stats_extracted_pmc.json "$DEST/out/" 2>/dev/null || true
cp out/swevo/*.json out/swevo/*.csv "$DEST/out/swevo/" 2>/dev/null || true
rm -f "$DEST/out/swevo/refcheck.json" "$DEST/out/swevo/numbers.json" "$DEST/out/swevo/style.json"
cp paper/swevo/numbers.tex "$DEST/paper/swevo/"
cp README_RELEASE_SWEVO.md "$DEST/README.md"
cp LICENSE "$DEST/LICENSE"

# ("Nguyen et al." inside a source paper's caption text is a cited author, not an identity)
if grep -r -n -i -E "thanh|nguyen|felice|tsinghua|talyxion|holy_grail|beetrade|sk-b80" "$DEST" --include="*.py" --include="*.sh" --include="*.md" --include="*.csv" --include="*.json" --include="*.tex" | grep -v -i "nguyen et al" | grep -v "ec_bestiary.json" | cut -d: -f1 | sort -u | grep .; then
  echo "identifying strings above: fix before pushing"; exit 1
fi
du -sh "$DEST"
echo "release tree at $DEST"
