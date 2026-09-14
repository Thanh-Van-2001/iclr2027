# OpenReview — ICLR 2027 (abstract deadline 2026-09-18 AOE, full paper 2026-09-25 AOE)

Copy each field below into the form. Every number in the abstract is the built value from numbers.tex.

## Title
Most Highlighted Comparisons Cannot Be Checked From the Printed Page

## Abstract
Machine learning decides what to believe by comparing numbers in tables. We ask how many of those comparisons a reader could check. From 2895 papers accepted at NeurIPS and ICML we extract the results tables whose bold marks a winner and identify the claim each makes: the value the authors set in bold against the best value they did not. Then we ask whether the paper prints what a test of that claim would need—an error bar on each of the two values, and the number of runs behind them. Of 32300 highlighted comparisons in the 2025 sample, 78.6% carry no error bar on either side as read, 65.6–77.5% once the instrument’s measured recall is propagated, and 16.9% can be tested from what is printed. Of those that can be tested, which come from 245 papers, 47.6% are not distinguishable from zero by Welch’s t at the stated run counts on the authors’ own numbers (40.2% by a two-sample z that takes the printed deviations as exact; 42.8–55.7% once the instrument’s measured verdict and testability error is propagated), and 60.6% (48.1%) once the other comparisons in the same table are accounted for. Where a caption names its benchmark, the split size alone says what is significant on it: 46.9% of those gaps are not, under independence, 24.3% under paired scoring. Neither headline is precise, and neither can be. Across conventions the source papers leave unstated, the failure rate spans 40.2% to 55.3% and the checkable share 5.4% to 19.5%, both far wider than sampling error: the papers do not print enough to pin down their own claims. On a reference set drawn after the pipeline was frozen, an image-based reader agrees with it on the verdict in 97.1% of the comparisons both can test and on every field of the claim in 69.7%; on random pages it finds about twice the highlighted comparisons the pipeline does, with the same shares. A second sample of 1097 papers from 2024 gives 79.3% and 48.5%. We release the pipeline, the per-comparison database, the rendered tables on which the instrument was scored, and the sixteen parser bugs that looking at them caught, at https://anonymous.4open.science/r/checkable--E2C5.1

## TL;DR (one sentence, <= 250 chars)
Of 32,300 bold-marked comparisons in NeurIPS/ICML 2024-25 tables, most print no error bar, and about half of those that can be tested are not distinguishable from zero on the authors' own numbers.

## Keywords
reproducibility; statistical significance; error bars; meta-science; benchmark reporting; results tables; audit

## Primary area (pick one)
"Other topics in machine learning" or, if offered, "Datasets and benchmarks" / "Reproducibility". Choose the one whose description mentions evaluation practice or reproducibility.

## Other fields
- Authors: fill in on OpenReview only (the PDF is anonymous; do not add names to the PDF).
- Code / supplementary URL: https://anonymous.4open.science/r/checkable--E2C5
- Reciprocal reviewing / LLM-use / ethics checkboxes: answer truthfully; the PDF's AI-use statement names Claude Opus 5 (reader, writing assistance), Claude Sonnet 5 and Gemini 3.1 Pro (second and third readers).
- Only title + abstract are needed by 18/09; the PDF can be uploaded or replaced until 25/09.
