# Bold Without Bars: What Three Years of AAMAS Tables Let a Reader Check

Code, data and audits for the paper. Everything a number in the paper rests on
is here; `run_all_aamas.sh` regenerates every number and the LaTeX macros from
the extraction file and the audit labels, without touching the network.

## Layout

- `study/` — the instrument, unchanged from the commit it was frozen at: the
  PDF table parser (`extract.py`), the comparison rules and tests
  (`analyze.py`), the sensitivity and conventions analyses, and the
  reference-set tooling (`gold_set.py`, `sample_pages.py`, `pages_score.py`).
- `aamas/` — what is specific to this paper: the IFAAMAS proceedings index
  (in `study/harvest.py`, `aamas_index`), the analysis driver
  (`make_all_aamas.py`), the evaluation-protocol scan (`protocol.py`), the
  community classifier (`classify.py`), the macro generator, the figures, the
  gate (`check_aamas.py`).
- `data/extracted_aamas.jsonl` — every table cell the parser read from the
  827 main-track papers of AAMAS 2024–2026, with position, bold flag, mean and
  bar. Rebuild it with
  `python study/pipeline.py --source aamas2024 --source aamas2025 --source aamas2026 --out data/extracted_aamas.jsonl --cache-pdfs data/corpus`.
- `out/aamas/` — every run record: the per-comparison database
  (`analysis.json`), `extra.json` (census, per-year, per-community, span,
  protocol resolution, funnel), `protocol.json` (every matched episode and
  seed sentence), `communities.csv` (the model's label per paper),
  `gold_set.json`, `gold_set_gemini.json` and `gold_set_pages.json` (the
  reference-set and pilot scores), `gold_set_census.json` (the census
  scored against the parser), `protocol_reader.json` (the model's reading
  of each rate paper's evaluation protocol).
- `audits/aamas_gold/` — the 140 reference items: rendered crops with the
  audited cell boxed, the run sentences, `items.json` (the parser's reading)
  and `labels.csv` (the reader's).
- `audits/aamas_gold_gemini/` — the second reader's labels on the same
  reference items (`labels.csv`).
- `audits/aamas_pages/` — the 100 random pilot pages, rendered, with the
  first reader's end-to-end labels (`labels.json`).
- `audits/aamas_census/` — the census: every caption page (`items.json`,
  1008 pages) with the second reader's labels (`labels.json`, merged from
  the per-shard files by `aamas/merge_census.py`). `aamas_census_retry/`
  lists the 15 pages re-read at reasoning effort `low`;
  `aamas_census_effort/` the 40 pages read again at `low` to measure what
  the setting changes (`draw.json` records the draw);
  `aamas_testable_pages/` the 66 pages holding parser-testable comparisons,
  read twice. The page images are not shipped (they run to hundreds of
  megabytes); `python aamas/sample_all_caption_pages.py` and
  `python aamas/sample_testable_pages.py` render them again from
  `data/corpus`, and the scores in `out/aamas/gold_set_census.json`,
  `gold_set_testable_pages.json`, `reader_retest.json` and
  `reader_effort.json` need only the labels.
- `audits/aamas_comm_check/` — the 100 first pages read by the second
  community labeller and its labels.
- `out/both_years.json`, `out/extra_stats.json` — the NeurIPS/ICML 2025
  records the side-by-side reads (from the concurrent submission's release).
- `paper/aamas/numbers.tex` — the macros as built.

## Reproduce

    pip install -r requirements.txt
    sh run_all_aamas.sh

The reader protocols (verbatim prompts) are in the supplementary PDF; the
reader and the classifier are language models named there, and every answer
they gave is in the files above.
