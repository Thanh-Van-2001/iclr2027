# OpenReview — AAMAS 2027 (abstract 2026-10-01 AoE, paper 2026-10-08 AoE)
Site: https://openreview.net/group?id=ifaamas.org/AAMAS/2027/Conference — Research Paper Track.
All authors need an OpenReview profile by 17 Sep 2026.

## Title
Bold Without Bars: What Three Years of AAMAS Tables Let a Reader Check

## Abstract (built values, 374 words)
A results table marks a winner in bold and asks the reader to believe it. We ask how often the page prints what checking would need. A text-layer parser, frozen before it met this corpus, reads every maintrack paper in the AAMAS proceedings of 2024, 2025 and 2026 (827 papers), finds the results tables whose bold marks a winner, and sets each bold cell against the best value the authors did not mark. Of the 2109 highlighted comparisons it reads, 57.2% print no error bar on either side (56.3% with the records a reference set showed to be artefacts removed; 43.7% implied by an image-based reader’s census of random pages) and 31.2% can be tested from the page (8.7% [1.0, 20.9] by the reader’s census). Every testable comparison comes from 66 papers, most of them in multi-agent learning, and 52.5% of them are not distinguishable from zero by Welch’s 𝑡at the authors’ own run counts, 65.0% where three seeds or fewer are stated and 33.7% at six or more. At the level of the paper, AAMAS and the main text of 1798 NeurIPS and ICML papers of 2025 print a ± cell at similar rates (18.9% against 17.2%); among the comparisons the parser reads, AAMAS carries bars more often and the bars support the claim no more often, a comparison the parser’s unequal coverage of the two formats qualifies. Win and success rates carry a second resolution that needs no error bar, the binomial noise of the evaluation protocol; among the 38 papers that highlight a rate, a language model finds the number of evaluation episodes stated in 13, and on their comparisons 42.7% of the highlighted gaps fall below what that many episodes can resolve. On a reference set drawn from the corpus, the image-based reader agrees with the parser on the whole claim in 90.5% [83.0, 94.9] of comparisons and on the verdict in 98.7% of those both can test; on random two-column pages the parser lists 18.2% of the single-bold groups the reader lists. Every number is a statement about what the parser reads, with that precision and that coverage, and the paper says which way each bias runs. We release the pipeline, the per-comparison database and the rendered reference set.

## Keywords
empirical methodology; reproducibility; statistical significance; multi-agent reinforcement learning; evaluation protocols; error bars

## Files
- Main PDF: D:/iclr2027/paper/aamas/main.pdf (8 pages incl. references; anonymous sigconf template)
- Supplementary zip: paper/aamas/supplement.pdf + code pointer (release repo Thanh-Van-2001/checkable-aamas, private; make an anonymous.4open.science mirror before submitting and cite it)
- Student-author box: tick if the primary author is a student.
