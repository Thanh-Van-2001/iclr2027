# Sealed machine readings: do not give to annotators

These files hold, for every item of the human kits, what the machines read: the parser's values and
verdicts (from the frozen `out/aamas/analysis.json` and `audits/aamas_gold/items.json`), both
reference readers' labels, the census reader's and the pilot reader's page labels, and the mapping
from blind ids to reference ids and strata. `aamas/human_validation_score.py` compares human labels
against them once the labels are collected.

They are copies, made by `python aamas/human_validation_kits.py build`; each file records its
sources and their SHA-256. Nothing here is edited by hand, and nothing here may be shown to an
annotator before their labels are frozen. The packed annotator folders
(`python aamas/human_validation_kits.py pack ...`) never include this directory.

| file | kit | content |
|---|---|---|
| `comparison_key.json` | A | blind id -> reference id, stratum, paper, core/overlap flags, parser values and frozen test, both readers' labels |
| `page_key.json` | B | page id -> source page, frame, caption pages in the paper, parser comparisons on the page (with winner cell coordinates), census and pilot / non-caption reader tables |
| `runcount_key.json` | C3 | item -> reference id, which pairs disagree, the parser's and both readers' run counts |
| `bartype_key.json` | C4 | table -> paper rank in the seeded order, why it is in the pool, the parser's comparisons on it |
