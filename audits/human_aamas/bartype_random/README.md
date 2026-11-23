# C4. A random set of unlabelled or disputed bar kinds

**Pool.** Tables (paper, table, page) on which the frozen parser read an error bar on both sides of
at least one comparison and found no statement of what the bar is (`dispersion_kind = unknown`;
the paper reads such a bar as a standard deviation). That gives 27 tables. To them are added the
reference-set tables whose bar kind the two readers labelled differently (3 tables). The pool holds
30 tables in 19 papers (`manifest.json`).

**Draw.** The unit is the paper, because the whole PDF's methodology decides. The 19 papers are put
in a seeded random order (seed 20261130). The first 12 papers (16 tables) are the core sample, and
the other 7 papers (14 tables) are a reserve. If the reserve is used, take it strictly in that
order, so that any prefix remains a simple random sample of papers; the scorer warns when the
labelled papers are not a prefix.

**Task.** For each table: find it in the PDF, read the experimental setup, captions, footnotes and
appendix, decide what the bars mean (`sd`, `se`, `ci`, `range`, `iqr`, `other`, `not_stated`,
`conflicting`), and quote the shortest passage that settles it with its location (or record what
was searched). No image is shipped, because this decision cannot be made from a crop.

**Scoring.** The scorer counts the bar kinds and reports how often a kind is stated at all and how
often it is SE or CI. As a labelled sensitivity it also reports how the verdicts of the parser's
comparisons on these tables change if the human's bar kind replaces the SD reading. That figure
mixes the human's bar kind with the parser's values. The sealed parser readings are
`../machine_keys/bartype_key.json`.
