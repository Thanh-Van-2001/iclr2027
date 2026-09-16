# OpenReview — AAMAS 2027 (abstract 2026-10-01 AoE, paper 2026-10-08 AoE)
Site: https://openreview.net/group?id=ifaamas.org/AAMAS/2027/Conference — Research Paper Track.
All authors need an OpenReview profile by 17 Sep 2026.

## Title
Bold Without Bars: What Three Years of AAMAS Tables Let a Reader Check

## Abstract (built values, 288 words; limit 300)
A results table marks a winner in bold and asks the reader to believe it. We ask how often the paper prints what checking would need, over the 827 main-track papers of AAMAS 2024–2026, with two instruments: a frozen text-layer parser, and an image-based reader that read every page holding a table caption. In every row or column with one bold cell, the bold value is set against the best unmarked value. A reader who finds such a cell can check it from the paper about one time in three by either instrument (32.8% of the reader’s comparisons carry two error bars and a run count, 31.2% of the parser’s), from the table’s own page about one time in six; most of the rest print no bar. Where the check can be made it fails about as often as it passes: 54.2% of the reader’s testable comparisons and 52.5% of the parser’s are not separable from their rival at 𝑝< 0.05 by Welch’s 𝑡at the stated run count, and the rate is highest at three seeds or fewer. The two image-based readers agree on every group’s verdict where both list a page. AAMAS and the NeurIPS/ICML mainstream print a ± cell at similar rates per paper; the highlighted comparisons of AAMAS carry bars more often, and the bars support the claim no more often. A win rate over 𝐾 episodes has a binomial resolution that needs no error bar: of the 20 papers that highlight one, 8 state 𝐾, and on their comparisons about half of the highlighted gaps fall below what the stated episodes resolve, a share that rests on eight papers and moves with a seed count the page does not always give. Everything is released.

## Keywords
empirical methodology; reproducibility; statistical significance; multi-agent reinforcement learning; evaluation protocols; error bars

## Files
- Main PDF: D:/iclr2027/paper/aamas/main.pdf (main text ends on page 8, references on page 9; anonymous sigconf template)
- Supplementary zip: paper/aamas/supplementary.zip (supplement.pdf, run records, audit labels; 1.4 MB) + code pointer (release repo Thanh-Van-2001/checkable-aamas, private; make an anonymous.4open.science mirror before submitting and cite it)
- Student-author box: tick if the primary author is a student.
