#!/bin/sh
# Regenerate every derived number of the metaheuristics paper from
# data/extracted_oa.jsonl, the text scan, the kind labels and the audit
# labels, then the LaTeX macros. Deterministic; nothing here touches the
# network. Building the corpus itself is
#   python swevo/harvest_oa.py ; python swevo/fetch_oa.py --journal "Scientific Reports"
#   python study/pipeline.py --source swevo-oa --cache-pdfs data/corpus_oa --cached-only --out data/extracted_oa.jsonl
# and the readings that need a model go through the relay:
#   python swevo/classify.py --journal "Scientific Reports" --shard k/4 --out out/swevo/kinds_shard$k.csv
#   python swevo/test_reader.py ; python study/read_pages_api.py --kit audits/swevo_census ...
set -e
if [ -d data/corpus_oa ]; then python swevo/text_scan.py > /dev/null; fi
python swevo/make_all_swevo.py
if [ -f audits/swevo_gold/labels_gemini.csv ]; then
python study/gold_set.py score --items audits/swevo_gold/items.json --labels audits/swevo_gold/labels_gemini.csv --exclude-unboxed --out out/swevo/gold_set.json > /dev/null
fi
if [ -f audits/swevo_gold/labels_sonnet.csv ]; then
python study/gold_set.py score --items audits/swevo_gold/items.json --labels audits/swevo_gold/labels_sonnet.csv --exclude-unboxed --out out/swevo/gold_set_sonnet.json > /dev/null
python study/gold_set.py agree --a audits/swevo_gold/labels_gemini.csv --b audits/swevo_gold/labels_sonnet.csv > out/swevo/reader_agreement.json
fi
if ls audits/swevo_census/labels_shard*.json > /dev/null 2>&1; then
python swevo/merge_census.py > /dev/null
python study/pages_score.py --items audits/swevo_census/items.json --labels audits/swevo_census/labels.json \
    --analysis out/swevo/analysis.json --extremal-only --out out/swevo/gold_set_census.json > /dev/null
python swevo/census_readings.py > /dev/null
if ls audits/swevo_verdict/labels_shard*.json > /dev/null 2>&1; then python swevo/verdict_crosstab.py > /dev/null; fi
if [ -f audits/swevo_human/labels.csv ]; then python swevo/human_score.py > /dev/null; fi
if [ -f audits/swevo_human_rows/labels.csv ]; then python swevo/human_score.py --kit audits/swevo_human_rows > /dev/null; fi
fi
python swevo/make_numbers_swevo.py
echo "numbers regenerated -> paper/swevo/numbers.tex"
