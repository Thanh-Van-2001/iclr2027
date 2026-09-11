#!/bin/sh
# Regenerate every derived number and rebuild the paper, from the two extraction
# files. Deterministic: the bootstrap is seeded and nothing here touches the
# network. Building the corpus itself is study/pipeline.py, which does.
set -e
python study/make_all.py
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
