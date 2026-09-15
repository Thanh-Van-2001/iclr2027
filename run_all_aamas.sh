#!/bin/sh
# Regenerate every derived number of the AAMAS paper from data/extracted_aamas.jsonl
# and the audit labels, then the LaTeX macros. Deterministic; nothing here
# touches the network. Building the corpus itself is
#   python study/pipeline.py --source aamas2024 --source aamas2025 --source aamas2026 \
#       --out data/extracted_aamas.jsonl --cache-pdfs data/corpus
# and the protocol scan and community labels need the cached PDFs:
#   python aamas/protocol.py ; RELAY_API_KEY=... python aamas/classify.py
set -e
python aamas/make_all_aamas.py
python study/gold_set.py score --items audits/aamas_gold/items.json --labels audits/aamas_gold/labels.csv --exclude-unboxed --out out/aamas/gold_set.json > /dev/null
python study/pages_score.py --items audits/aamas_pages/items.json --labels audits/aamas_pages/labels.json \
    --analysis out/aamas/analysis.json --out out/aamas/gold_set_pages.json > /dev/null
if [ -f audits/aamas_gold_gemini/labels.csv ]; then
python study/gold_set.py score --items audits/aamas_gold/items.json --labels audits/aamas_gold_gemini/labels.csv --exclude-unboxed --out out/aamas/gold_set_gemini.json > /dev/null
python study/gold_set.py agree --a audits/aamas_gold/labels.csv --b audits/aamas_gold_gemini/labels.csv > out/aamas/reader_agreement_gemini.json
fi
if [ -f audits/aamas_testable_pages/labels.json ]; then
python study/pages_score.py --items audits/aamas_testable_pages/items.json --labels audits/aamas_testable_pages/labels.json     --analysis out/aamas/analysis.json --out out/aamas/gold_set_testable_pages.json > /dev/null
fi
if ls audits/aamas_census/labels_shard*.json > /dev/null 2>&1; then
python aamas/merge_census.py > /dev/null
python study/pages_score.py --items audits/aamas_census/items.json --labels audits/aamas_census/labels.json     --analysis out/aamas/analysis.json --out out/aamas/gold_set_census.json > /dev/null
python aamas/reader_retest.py > /dev/null
if [ -f audits/aamas_census_effort/labels.json ]; then
python aamas/reader_retest.py --first audits/aamas_census --second audits/aamas_census_effort --out out/aamas/reader_effort.json > /dev/null
fi
fi
python aamas/figures.py
python aamas/supplement_tables.py
python aamas/make_numbers_aamas.py
python aamas/check_aamas.py "$@"
cd paper/aamas && latexmk -pdf -interaction=nonstopmode -halt-on-error supplement.tex > build_supp.log 2>&1 && cd ../..
python aamas/make_supplementary.py
