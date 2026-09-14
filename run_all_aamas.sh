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
python study/gold_set.py score --items audits/aamas_gold/items.json --labels audits/aamas_gold/labels.csv --out out/aamas/gold_set.json > /dev/null
python study/pages_score.py --items audits/aamas_pages/items.json --labels audits/aamas_pages/labels.json \
    --analysis out/aamas/analysis.json --out out/aamas/gold_set_pages.json > /dev/null
python aamas/figures.py
python aamas/make_numbers_aamas.py
python aamas/check_aamas.py "$@"
