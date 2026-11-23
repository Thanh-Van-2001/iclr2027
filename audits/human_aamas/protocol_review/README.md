# C2. Protocol review of the 20 rate papers

The kit is the existing `../protocol_check.csv`. It is unchanged, and its layout and guide are in
`../README_VI.md` (section A). Each row is a paper with a win/success-rate comparison, with the
model's reading of K (episodes per rate), seeds, sampled or fixed instances, shared instances and
what the deviation is over, pre-filled. The human confirms (`same`) or corrects each from the PDF.

Because the model's values are visible, this is a **human review and correction of a model
reading, not blind ground truth**, and the scorer reports it that way. The 8 papers with a
model-read K come first in the CSV; do those first.

`protocol_links.csv` adds the public PDF URL of each paper (the CSV's `pdf` column is a local path
into `data/corpus/`, which is not shipped). Score with `python aamas/human_score.py` (the existing
scorer) or `python aamas/human_validation_score.py` (the same counts with Wilson intervals and the
8-paper subset).
