# B. Every eligible group on random pages

A person lists, on each whole page, every table and every group with exactly one bold cell,
marks whether that bold value is strictly the best, and clicks it on the page image. A page with
no eligible group needs that status set explicitly, plus a note on what is on the page. Only once
the labels are frozen does the scorer match the person's groups against the parser's comparisons
and the two readers' groups on the same page.

## Draw (`manifest.json`)

- **P01-P30, set "core"**: 30 of the 100 pilot caption pages of `audits/aamas_pages`, a simple
  random sample with seed 20261126. The pilot drew one page per paper uniformly among the paper's
  pages that hold a `Table N:` caption line, so each page is a different paper. The 35 hard-case
  pages played no part in the draw. Four drawn pages (P09, P12, P15, P19) are also hard-case pages;
  they are kept, and flagged in the key.
- **P31-P50, set "extra"**: 20 of the 100 pages of `audits/aamas_noncaption`, which are random pages
  on which the parser detected no caption (seed 20261127). This is a separate stratum, scored
  separately, for a statement about pages outside the caption frame.
- **overlap**: 8 of the 30 caption pages (seed 20261128) for a second annotator.

The ids and set names carry no machine reading. Images are byte-identical copies of the shipped
renders (zoom 2.0, so 1 image pixel = 0.5 pt), and clicks are stored in image pixels.

## Eligible group (the paper's unit)

A row or column of a results table (`results_table = y`) whose caption does not give bold another
meaning (`bold_rule = single_best`), with exactly one bold cell and at least one non-bold number,
where the bold value is strictly the best in the metric's direction (`bold_is_best = y`). Other
single-bold groups are listed too, with `n`, `tie` or `unclear`. They are counted, but they do not
enter recall or precision.

## Scoring

Matching is one-to-one on equal bold values, the rule of `study/pages_score.py`. Where a value
occurs twice, the parser comparison whose winner cell lies nearest the click is taken. Recall is the
share of the person's eligible groups that a machine also lists. Precision is the share of the
machine's groups that the person lists. Both come with Wilson and page-bootstrap intervals, and the
caption frame also gets a version weighted to all caption pages. False negatives and false positives
are listed in `out/aamas/human_validation/page_groups_matched.csv`. The sealed machine readings are
`../machine_keys/page_key.json`.
