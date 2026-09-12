# Most Highlighted Comparisons Cannot Be Checked From the Printed Page

Code, extraction files and reference sets for the paper of that title
(submitted to ICLR 2027, double blind). Every number in the paper is a macro
in `paper/submission/numbers.tex`, each annotated with the run that produced
it; `run_all.sh` regenerates all of them from the two extraction files in
`data/`.

## What is here

| path | what |
| --- | --- |
| `study/pipeline.py`, `study/harvest.py`, `study/extract.py` | corpus draw, PDF download, table and claim extraction (network) |
| `data/extracted_2025.jsonl`, `data/extracted_2024.jsonl` | the extraction files: one record per paper, every table, every cell |
| `study/analyze.py` | claim unit, orientation and direction, the test (Welch's *t* at the stated run count, *z* in the normal limit), Holm within table |
| `study/sensitivity.py`, `study/extra_stats.py` | every row of the conventions table, the imputed-noise comparison, subfield and ablation splits |
| `study/binomial_check.py`, `study/benchmark_resolution.py`, `study/resolution_table.py` | what a benchmark's split size can resolve |
| `study/gold_set.py` | draws, renders and scores the reference sets |
| `study/latex_crosscheck.py` | the cross-check against arXiv LaTeX source (`--offline` uses the cached sources) |
| `study/make_numbers.py` | writes `numbers.tex` from the JSON outputs; a number typed by hand fails the build |
| `audits/gold_a`, `audits/gold_b`, `audits/gold_d` | development, held-out and frozen reference sets: rendered table crops with the pipeline's cell boxed, the reader's labels, the pipeline's values |
| `audits/gold_c` | the run-count audit (both bars, no count found) |
| `audits/gold_b/run_count_adjudication.json` | the whole-paper adjudication of disputed run counts |
| `audits/recall` | the contact sheets of the recall audit and their manifest |
| `audits/latex_source/cache.json` | the cached arXiv table environments |
| `audits/human` | the answer sheet and instructions for a human reading of the frozen set |
| `tests/test_extract.py` | one regression test per extractor bug described in the paper |

The frozen set (`audits/gold_d`) was drawn after the released pipeline was
tagged and nothing was fixed on it; the failure modes it exposed are listed in
the paper and left in the code.

## Rebuilding the numbers

    pip install -r requirements.txt      # PyMuPDF, matplotlib
    sh run_all.sh                        # analysis, audits, macros; then the LaTeX build, which needs the paper source

`run_all.sh` ends by compiling the paper; without the paper source the last
step fails harmlessly after `paper/submission/numbers.tex` has been rewritten.
Rebuilding the corpus itself from the proceedings is
`python study/pipeline.py --sources neurips2025 icml2025 --sample 2000 --seed 0`;
it downloads about two thousand PDFs and takes hours.

## Reading a reference-set item

Each item in `audits/gold_*/items.json` names a paper, a page and a table and
carries the pipeline's values; `img/<id>_<stratum>.png` is the rendering the
reader saw and `img/<id>_runs.txt` the run-count sentences it was given.
`labels.csv` holds the reader's answers; `python study/gold_set.py score`
compares the two and `python study/gold_set.py agree` compares two readers.
