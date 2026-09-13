# Human verification kit (frozen set D, 60 items)

The same sixty items the three machine readers labelled (`audits/gold_d`,
`audits/gold_d_reader2`, `audits/gold_d_gemini`): the first forty testable
comparisons and the first twenty no-bar comparisons of the frozen set.

- `labels.csv`: blank template for a blind, field-by-field labelling, scored by
  `python study/gold_set.py score --items audits/gold_d/items.json --labels audits/human/labels.csv`.
- `verify_pass1.csv`: one author's single verification pass (the pipeline's
  reading shown, one key per item: correct / wrong / unclear), made in under
  four minutes and disowned by its author before scoring. It is kept as a
  record and no number in the paper rests on it; `study/human_verify_score.py`
  scores it and reports its agreement with the machine readers' majority
  (`out/human_verify_pass1.json`).
- `verify_marks.json`: where the runner-up cell was boxed for that pass.

The rendered items are in `audits/gold_d/img`. `study/human_kit_html.py` and
`study/human_verify_kit.py` regenerate the labelling pages.
