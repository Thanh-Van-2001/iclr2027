# OpenReview — AAMAS 2027 (abstract 2026-10-01 AoE, paper 2026-10-08 AoE)
Site: https://openreview.net/group?id=ifaamas.org/AAMAS/2027/Conference — Research Paper Track.
All authors need an OpenReview profile by 17 Sep 2026.

## Title
Bold Without Bars: What Three Years of AAMAS Tables Let a Reader Check

## Abstract (built values, 296 words; limit 300)
A results table marks a winner in bold and asks the reader to believe it. We ask how often the page prints what checking would need. A frozen text-layer parser reads every main-track paper in the AAMAS proceedings of 2024–2026 (827 papers), finds the results tables whose bold marks a winner, and sets each bold cell against the best value the authors did not mark. Of the 2109 highlighted comparisons it reads, 57.2% print no error bar on either side (43.7% by an image-based reader’s census of random pages) and 31.2% can be tested from the page. Every testable comparison comes from 66 papers, and 52.5% of them are not distinguishable from zero by Welch’s 𝑡at the authors’ own run counts: 65.0% where three seeds or fewer are stated, 33.7% at six or more. AAMAS and the main text of 1798 NeurIPS and ICML papers print a ± cell at similar rates per paper; among the comparisons the parser reads, AAMAS carries bars more often and the bars support the claim no more often. Win and success rates carry a second resolution that needs no error bar, the binomial noise of the evaluation protocol; of the 38 papers that highlight a rate, a language model finds the number of evaluation episodes stated in 13, and on their comparisons 42.7% of the highlighted gaps fall below what that many episodes can resolve. On a reference set the reader agrees with the parser on the whole claim in 90.5% [83.0, 94.9] of comparisons and on the verdict in 98.7%; on random two-column pages the parser lists 18.2% of the groups the reader lists. Every number is a statement about what the parser reads, with that precision and coverage. We release the pipeline, the database and the reference set.

## Keywords
empirical methodology; reproducibility; statistical significance; multi-agent reinforcement learning; evaluation protocols; error bars

## Files
- Main PDF: D:/iclr2027/paper/aamas/main.pdf (8 pages incl. references; anonymous sigconf template)
- Supplementary zip: paper/aamas/supplement.pdf + code pointer (release repo Thanh-Van-2001/checkable-aamas, private; make an anonymous.4open.science mirror before submitting and cite it)
- Student-author box: tick if the primary author is a student.
