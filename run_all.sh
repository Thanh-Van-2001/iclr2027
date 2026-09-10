#!/bin/sh
# Regenerate every derived number and rebuild the paper, from the two extraction
# files. Deterministic: the bootstrap is seeded and nothing here touches the
# network. Building the corpus itself is study/pipeline.py, which does.
set -e
python study/make_all.py
python study/binomial_check.py
python study/benchmark_resolution.py
python study/make_numbers.py
python study/figures_paper.py --analysis out/analysis_2025.json \
    --run-id survivability_both_years --out-dir paper/submission/figures
( cd paper/submission && latexmk -pdf -interaction=nonstopmode main.tex )
./check.sh
