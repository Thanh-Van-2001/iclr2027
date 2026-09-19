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
  (the second labeller on a random hundred) and `kinds2_shard*.csv` /
  `kinds2_merged.csv` (the second labeller over the whole corpus), `test_reader.json` (the model's reading of each
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
- `audits/swevo_census_rows/`, `audits/swevo_census_rows2/` — the re-read
  of the Mean/Std-row pages under `instruction.txt`, merged table by table
  into the census by `swevo/census_readings.py` (the merge rule is in the
  paper); `audits/swevo_verdict/` — the model's reading of the printed
  verdicts for `swevo/verdict_crosstab.py`.
- `audits/swevo_human/`, `audits/swevo_human_rows/` — the two labelling kits
  (100 separate-column groups, 100 Mean/Std-row groups): `label.html` opens
  in a browser and writes `labels.csv`; `python swevo/human_score.py [--kit
  audits/swevo_human_rows]` scores it; `swevo/kit_refresh.py` recomputed the
  rows kit's strata and added the whole-row question to both sheets after
  the draw. `labels_claude-sonnet-5.csv` is a
  second vendor's model answering the same kit (`swevo/kit_reader.py`),
  reported in the paper as a model check and not as a human label.
- `data/extracted_pmc.jsonl`, `out/swevo/text_scan_pmc.json`,
  `out/swevo/kinds_pmc_*.csv`, `out/swevo/fetch_pmc_cloud_log.json` — the
  349 papers of Biomimetics and PeerJ Computer Science fetched after review
  through PMC's cloud bucket (`swevo/fetch_pmc_cloud.py`): the parser, the
  scan and the classifier on them, reported as a contrast and not folded
  into the corpus.
- `audits/swevo_census_cols/` — the one-question re-read of every
  column-oriented census table (does every bold cell lie in one row or
  column, and under which label; `swevo/wholerow_reader.py`), asked after
  review.
- `audits/swevo_markers/adjudicate.csv` — the papers on which the two
  full-text readers disagree about whether a per-cell verdict is printed
  (every disagreement one way), with both readers' quoted sentences, for a
  person to adjudicate from the PDF (`swevo/markers_kit.py`).
- `paper/swevo/numbers.tex` — the generated macro file; every number in the
  paper is one of these, with its run record named in the comment above it.

## Regenerating

```
pip install -r requirements.txt
sh run_all_swevo.sh
```

Rebuilding the corpus needs the network: `python swevo/harvest_oa.py`, (`python swevo/fetch_pmc_cloud.py` for the two PMC-mirrored journals), then
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
