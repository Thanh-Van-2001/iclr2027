# The Convention on the Page: an Audit of Open-Access Metaheuristics Papers

Code, data and audits for the paper. Everything a number in the paper rests on
is here; `run_all_swevo.sh` regenerates every number and the LaTeX macros from
the extraction file, the text scan, the kind labels and the audit labels,
without touching the network.

## Layout

- `study/` — the instrument, unchanged from the commit it was frozen at for
  the two companion audits: the PDF table parser (`extract.py`), the
  comparison rules and tests (`analyze.py`), the sensitivity analyses, the
  reference-set tooling (`gold_set.py`, `pages_score.py`) and the page reader
  (`read_pages_api.py`; this study passes `--bar-forms` to add the
  `separate_row` value to the protocol's vocabulary, nothing else changes).
- `swevo/` — what is specific to this paper: the OpenAlex listing
  (`harvest_oa.py`), the fetcher (`fetch_oa.py`), the full-text scan
  (`text_scan.py`: run counts, tests, suites, bestiary metaphors, methodology
  citations), the kind classifier (`classify.py`), the statistical-test
  reader (`test_reader.py`), the census kit (`census_kit.py`), the analysis
  driver (`make_all_swevo.py`), the census readings (`census_readings.py`),
  the macro generator (`make_numbers_swevo.py`), the gate (`check_swevo.py`).
- `swevo/PLAN.md` — the plan written before any corpus PDF was downloaded,
  with the deviations recorded in the paper.
- `out/swevo/index.json` — the 3,518 papers OpenAlex listed under the query;
  `data/extracted_oa.jsonl` — every table cell the parser read from the 1,642
  *Scientific Reports* papers, with position, bold flag, mean and bar.
- `out/swevo/` — every run record: `analysis.json` (the per-comparison
  database), `extra.json` (headline, by kind, by year, readings, text-scan
  blocks, citation blocks), `text_scan.json`, `kinds_merged.csv` and the
  per-shard `kinds_shard*.csv` (the first labeller), `kinds_second_sonnet.csv`
  (the second labeller), `test_reader.json` (the model's reading of each
  paper's runs, layout, test and bold rule), `gold_set*.json` (the
  reference-set and census scores), `census_readings.json`.
- `audits/swevo_gold/` — the 140 reference items: rendered crops with the
  audited cell boxed, the run sentences, `items.json` (the parser's reading)
  and the two readers' labels (`labels_gemini.csv`, `labels_sonnet.csv`).
- `audits/swevo_census/` — the census: every caption page of 500 randomly
  drawn papers (`items.json`, `draw.json`) with the reader's labels
  (`labels.json`, merged from the per-shard files by `swevo/merge_census.py`).
  The page images (700 MB) are regenerated from the PDFs by
  `python swevo/census_kit.py`.
- `paper/swevo/numbers.tex` — the generated macro file; every number in the
  paper is one of these, with its run record named in the comment above it.

## Regenerating

```
pip install -r requirements.txt
sh run_all_swevo.sh
```

Rebuilding the corpus needs the network: `python swevo/harvest_oa.py`, then
`python swevo/fetch_oa.py --journal "Scientific Reports"`, then
`python study/pipeline.py --source swevo-oa --cache-pdfs data/corpus_oa --cached-only --out data/extracted_oa.jsonl`.
The model readings (`swevo/classify.py`, `swevo/test_reader.py`,
`study/read_pages_api.py`, `study/read_kit_api.py`) go through an
OpenAI-compatible endpoint named by `RELAY_URL` and `RELAY_API_KEY`; the
model names are in the run records.

## Licence

MIT for the code; the extraction file and the labels are released under
CC BY 4.0. The source papers are CC BY 4.0 articles of *Scientific Reports*;
the corpus records their DOIs and the parser's reading of their tables, not
the articles themselves.
