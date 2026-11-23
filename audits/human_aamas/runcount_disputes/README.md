# C3. The 18 disputed run counts

Testable, boxed reference items on which the run count is disputed. A dispute is any of three
disagreements: the parser against the first reader (15 items), the parser against the second
reader (11), or the two readers against each other (9). Each pair is compared only when both sides
gave a readable answer, and for a reader only when it called the region a results table. The union
is 18 items. The join is exact, on the reference item id that `audits/aamas_gold/items.json`,
`audits/aamas_gold/labels.csv` and `audits/aamas_gold_gemini/labels.csv` share, and no fuzzy
matching is involved. The rule is `runcount_disputed_ids()` in `aamas/human_validation_kits.py`.
The reviews themselves are not in the repository, so the rule is our reconstruction of "the 18".
It is the only definition we found that the shipped files support, and it yields exactly 18.

For each item the annotator gets the crop, the PDF link at the table's page, and the sentences a
regular expression pulled out of the paper (seed, run, trial, episode; the same sentences the
paper's readers got). The sheet labels them as a search aid, not an answer. The annotator records
the count that applies to this table, what it counts (seeds, episodes, instances, ...), whether
the statement names this table, where it is stated, and a minimal quoted passage with its
location. The machine values and which pair disagrees stay sealed in
`../machine_keys/runcount_key.json` and appear only in the scorer's
`out/aamas/human_validation/runcount_decisions.csv`.

Order: R01-R18, a seeded shuffle (20261129). Ask annotators to finish kit A first, because these
18 items are also in A and seeing them here first would flag them as hard.
