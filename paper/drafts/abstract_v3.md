# Abstract, draft 3 — final pipeline, 1,796 papers

**Title**: Most Reported Improvements Cannot Be Checked

---

## Abstract

Machine learning decides what to believe by comparing numbers in tables. We ask
how many of those comparisons a reader could check. From 1,796 papers accepted
at NeurIPS and ICML 2025 we extract every results table, identify the claim each
one makes — the value the authors set in bold against the best value they did
not — and ask whether the paper prints what a test of that claim would need.
Usually it does not. Of 15,027 highlighted comparisons, 78.0% carry no error bar
on either side and a further 11.5% give an error bar but never say how many runs
produced it, leaving 8.3% that can be tested at all; only one accepted paper in
four prints an explicit error bar in any results table. Among the comparisons
that can be tested, 37.2% are not distinguishable from zero at the 5% level
using the authors' own numbers, and 44.0% once the median seven simultaneous
comparisons in the same table are accounted for — so multiplicity alone moves
one highlighted result in fifteen from significant to not. The failures are
concentrated where they matter: improvements that fail have a median size of
1.3% against 6.8% for those that survive, which is to say the margins that
decide leaderboard order are the ones the evidence cannot support. An
independent sample of 475 papers from 2024 gives the same picture, as do NeurIPS
and ICML taken separately. We release the pipeline, the per-comparison database,
and the record of three parser bugs that visual validation caught — each of
which had produced a confident and wrong version of these numbers.

---

## Where every number comes from

`results/survivability_2025_final-ee0ef07d.json`, content hash `26af791300fb1be5`.

| quantity | value |
| --- | --- |
| papers | 1,796 (NeurIPS 2025 + ICML 2025) |
| highlighted comparisons | 15,027 |
| neither side has an error bar | 78.0% |
| error bar but no number of runs | 11.5% |
| only one side has an error bar | 1.9% |
| testable | 8.3% (1,240, from 118 papers) |
| papers with an explicit error bar | 24.3% |
| papers stating a number of runs | 25.3% (median 10) |
| median comparisons per table | 7 |
| fail uncorrected | 37.2% |
| fail under Holm-Bonferroni | 44.0% |
| median gap, failing / surviving | 1.33% / 6.76% |
| 2024 replication | 84.1% neither side, 42.2% failing, n=475 |

## Notes on the prose

- Two short sentences set up the question before any number appears.
- "Usually it does not." lands after a long sentence. Read the paragraph aloud
  and that is where the reader breathes.
- The multiplicity result is given as "one highlighted result in fifteen"
  because 6.8 percentage points is a quantity nobody feels.
- The last sentence concedes that our own first three attempts were wrong. A
  reviewer who suspects the parser will find that we suspected it first.

## What is still missing before submission

1. **Extractor precision.** Two comparisons validated by eye on the final
   pipeline is not a number; it is an anecdote. The paper needs ~100, reported
   with a Wilson interval, and split by bucket — precision on "no error bar" is
   what the headline rests on.
2. **The 2024 arm** must be re-extracted through the fixed pipeline before it
   can be called a replication. The numbers quoted above came from the buggy
   parser and will move.
3. **118 papers** contribute all testable comparisons. State it plainly in the
   limitations rather than letting a reviewer discover it.
4. A **caliper test** on the distribution of gaps near zero would separate
   "small effects are hard to detect" from "small effects are reported because
   they cleared a threshold".
