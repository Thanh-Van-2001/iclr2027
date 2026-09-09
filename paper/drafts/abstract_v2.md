# Abstract, draft 2 — real numbers, 2025 corpus

**Title candidates**, best first:

1. Most Reported Improvements Cannot Be Checked
2. Nine in Ten Highlighted Comparisons Carry No Uncertainty
3. Unfalsifiable by Construction: Uncertainty Reporting at NeurIPS and ICML

---

## Abstract

Machine learning decides what to believe by comparing numbers in tables. We ask
how many of those comparisons a reader could check. From 1,869 papers accepted
at NeurIPS and ICML 2025 we extract every results table and identify the claim it
makes — the value the authors set in bold against the best value they did not —
and then ask whether the paper prints enough for that claim to be tested. Usually
it does not. Of 11,690 highlighted comparisons, 90.2% carry no measure of
uncertainty on either side, and only 2.3% can be tested at all, because a test
needs an error bar on both values and a number of runs; three quarters of papers
never state how many runs they did. Where a test is possible, 45.3% of the
highlighted improvements are not distinguishable from zero at the 5% level using
the authors' own error bars — before any correction for the five comparisons the
median table makes at once. The failures are concentrated where it matters: the
improvements that fail have a median size of 1.2% against 4.2% for those that
survive, so the margins that decide leaderboard order are exactly the ones the
evidence cannot support. An independent sample of 475 papers from 2024 gives the
same picture (26.5% of papers with error bars, 42.2% of testable comparisons
failing), as do NeurIPS and ICML separately. We release the extraction pipeline,
the per-comparison database, and the cases our extractor cannot parse.

---

## Notes on the prose

- Opens on how the field actually works, then the question. Nine words, then
  eleven. No "In recent years", no "remarkable success".
- "Usually it does not." — three words, after a forty-word sentence. The reader
  needs somewhere to land.
- Every claim carries its number inside the sentence that makes it.
- "the margins that decide leaderboard order are exactly the ones the evidence
  cannot support" is the sentence a reviewer will quote. It comes late, after
  the evidence, not in the first line as a promise.
- Replication is stated as a fact with numbers, not as "we further validate".
- The last sentence concedes a limitation rather than hiding it.

## Numbers used (all from results/survivability_2025-733755a8.json)

| quantity | value |
| --- | --- |
| papers | 1,869 (1,130 NeurIPS 2025, 739 ICML 2025) |
| highlighted comparisons | 11,690 |
| neither side has uncertainty | 90.2% |
| testable | 2.3% (267) |
| failing, uncorrected | 45.3% (121 of 267) |
| papers with explicit error bar | 25.6% |
| papers stating number of runs | 24.8% |
| median comparisons per table | 5 |
| median gap, failing / passing | 1.17% / 4.24% |
| 2024 replication | 26.5% error bars, 42.2% failing, n=475 |

## Still to do before this is submittable

- The 267 testable comparisons come from 65 distinct papers. State this in the
  abstract or expect a reviewer to find it. Consider raising the corpus.
- Hand-validate a random 100 extracted comparisons against the source PDFs and
  report extractor precision. Without this number the whole study is assertion.
- Decide the headline: "cannot be checked" (rests on all 1,869 papers) versus
  "does not survive" (rests on 65). The first is the stronger paper.
