# Abstract, draft 1 (numbers from the 475-paper pilot; to be refreshed on the full corpus)

**Title**: Most Reported Improvements Cannot Be Checked: Uncertainty Reporting in
Accepted Machine Learning Papers

Machine learning decides what to believe by comparing numbers in tables. We ask
how many of those comparisons a reader could verify. Taking every results table
in 475 papers accepted at NeurIPS and ICML 2024, we identify the comparison each
table makes -- the value the authors set in bold against the best value they did
not -- and ask whether the paper prints enough for that comparison to be tested.
It usually does not. In 84% of the 2,682 highlighted comparisons, neither the
winner nor the runner-up carries any measure of uncertainty; only 5% can be
tested at all, because a test needs an error bar on both sides and a number of
runs, and 72% of papers never state how many runs they did. Where a test is
possible, 42% of the highlighted improvements are not distinguishable from zero
at the 5% level using the authors' own error bars, before any correction for the
median of five comparisons each table makes simultaneously. The problem is not
that the field's error bars are wrong; it is that they are usually absent, and
absent asymmetrically -- papers that report uncertainty show a median relative
improvement of 4.0%, while the improvements that fail their own test have a
median of 0.7%. We release the extraction pipeline and the per-comparison
database, and we note that the same audit applied to this paper is the reason we
report what our own extractor cannot see.

---
## Notes on the writing

- The first sentence states the field's actual epistemics in nine words, then the
  question. No "In recent years".
- Every claim carries its number, in the sentence that makes the claim.
- "It usually does not" is four words after a long sentence. The rhythm matters.
- The limitation is the last sentence rather than a hidden appendix.
- Nothing here is hedged that does not need hedging; the one hedge that stays is
  "the problem is not that the field's error bars are wrong", because we did not
  test that and should not imply we did.

## Numbers to refresh once the full corpus lands
- n papers, n comparisons
- % neither side has uncertainty
- % testable
- % failing among testable
- median relative gap, overall and among failures
- n distinct papers contributing testable comparisons  <- the weak point
