#!/bin/sh
# Regenerate every derived number and rebuild the paper, from the two extraction
# files. Deterministic: the bootstrap is seeded and nothing here touches the
# network. Building the corpus itself is study/pipeline.py, which does.
set -e
python study/make_all.py
# Hand-judged audits live in audits/; their scores are derived here.
python study/gold_set.py recall --manifest audits/recall/manifest.json --analysis out/analysis_2025.json --out out/recall_v4.json > /dev/null
python study/gold_set.py score --items audits/gold_a/items.json --labels audits/gold_a/labels.csv     --out out/gold_set_devA_prefix.json > /dev/null
python study/gold_set.py score --items audits/gold_a/items.json --labels audits/gold_a/labels.csv     --rescore-with out/analysis_2025.json --out out/gold_set_devA_postfix.json > /dev/null
python study/gold_set.py score --items audits/gold_b/items.json --labels audits/gold_b/labels.csv     --out out/gold_set_heldout.json > /dev/null
python study/gold_set.py score --items audits/gold_b/items.json --labels audits/gold_b/labels.csv \
    --rescore-with out/analysis_2025.json --out out/gold_set_heldout_final.json > /dev/null
python study/extra_stats.py > out/extra_stats.log
python study/binomial_check.py
python study/benchmark_resolution.py
python study/resolution_table.py
python study/make_numbers.py
python study/figures_paper.py --analysis out/analysis_2025.json \
    --run-id survivability_both_years --out-dir paper/submission/figures
# Clean first: latexmk caches a previous failure and will otherwise report
# "up-to-date" while leaving a stale PDF built from the old macros, which is the
# worst kind of failure because everything looks fine.
( cd paper/submission && latexmk -C >/dev/null &&   latexmk -pdf -interaction=nonstopmode main.tex &&   bibtex main >/dev/null &&   latexmk -pdf -interaction=nonstopmode main.tex )
./check.sh
