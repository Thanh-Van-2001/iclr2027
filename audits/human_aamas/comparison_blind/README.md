# A. Blind re-reading of the 140 reference comparisons

Each item is one of the 140 boxed comparisons of `audits/aamas_gold` (100 drawn from the parser's
testable comparisons, 40 from its bar-less ones, after the parser was frozen). The annotator sees
the same crop the paper's readers saw (the audited bold cell boxed in red), the paper title, table
number and PDF page, and a link to the public PDF at that page. They see nothing else: no stratum,
no parser value, no reader label and no verdict. Ids `B001`-`B140` come from a seeded shuffle, and
the images were copied under those ids so that no file name reveals the stratum.

| file | what |
|---|---|
| `label.html` | the offline sheet (annotator ID, autosave, resume from CSV, export CSV) |
| `images/Bnnn.png` | byte-identical copies of `audits/aamas_gold/img/*.png` |
| `items.json` | what the sheet shows: id, item sets, title, table, PDF page, PDF URL, image |
| `labels_template.csv` | the exported layout, blank |
| `manifest.json` | seeds, draw rules, counts, sampling fractions, source hashes |
| `raw/` | one exported CSV per annotator, unchanged (frozen by `freeze`) |
| `adjudication.csv` | only if two annotators disagree and a third adjudicates; raw files stay as they are |

The sealed mapping (blind id to reference id, stratum, parser values, both readers' labels) is
`../machine_keys/comparison_key.json`. Annotators never receive it.

## Item sets

- **core** (100): 70 of the 95 boxed testable items and 30 of the 35 boxed bar-less items,
  simple random samples with seed 20261123. Sampling fractions 70/95 and 30/35. Results are
  reported **by stratum**. The testable stratum is oversampled on purpose relative to the corpus,
  and the two strata are never pooled.
- **overlap** (30 of the core): 21 + 9, seed 20261124, for a second annotator (21% of the kit,
  30% of the core).
- **optional** (40): the rest, including the 10 items the paper's kit rendered without a box.
  The first question voids them, as the paper does.

## Questions (all items get the same ones)

target visible; results table; bold cell bold and alone in its group (`y` / `not_bold` /
`several_bold`); orientation; direction; winner mean; winner bar present + value; runner-up mean
(best non-bold in the group, or `none`); runner-up bar present + value; runner-up copied from
another paper; what the error bar means (`sd`, `se`, `ci`, `unlabelled`, `other`, `absent`) and
where that is stated; run count (integer, `none`, `unclear`), other counts that might apply, and
where it is stated (`caption`, `page`, `elsewhere`, `absent`, `ambiguous`); whether the full paper
was opened; evidence (location + short quote); confidence; comment. `unclear` is always allowed;
the scorer counts it and never replaces it with a machine value.

Not shown: the run-count sentences `audits/aamas_gold/img/*_runs.txt`. They exist for the
testable stratum only, so showing them would reveal the stratum; the annotator searches the PDF.
