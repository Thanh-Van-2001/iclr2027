# Rebuttal draft: independent human validation (AAMAS 2027, submission 3154)

<!--
Every double-braced slot below is filled by `python aamas/human_validation_score.py`, ONLY from human
label files in audits/human_aamas/*/raw/ (and the two earlier kits). A slot with no human data
is printed as [PENDING: ...]; do not send any paragraph that still carries one. Never type a
number into this file by hand: change the labels, rerun the scorer, and use
out/aamas/human_validation/rebuttal_filled.md. The bracketed reviewer notes are for the authors
to complete from the reviews; they are not filled automatically.
-->

## What we did

After the reviews we had the paper's material re-read by people, not models. Annotator
{{A_annotator}} (independent of every machine reading: {{A_independent}}) re-read
{{A_items}} of the 140 reference comparisons ({{A_papers}} papers) from the rendered tables and
the full PDFs. They had no access to the parser's values, either reader's labels, the item's
stratum or any verdict. A second annotator independently re-read {{A_hh_items}} of the same items.
All draws are seeded and listed in `audits/human_aamas/*/manifest.json`. The raw label files are
frozen by hash, and adjudication is kept in a separate file.

## Reference comparisons, field by field (testable stratum, {{A_testable_items}} items)

Human against the parser, items both answered, Wilson 95% and paper-cluster bootstrap intervals:

| field | agreement |
|---|---|
| bold cell is the single bold of its group | {{A_T_bold_unique}} |
| orientation | {{A_T_orientation}} |
| direction | {{A_T_direction}} |
| winner mean | {{A_T_winner_mean}} |
| runner-up mean | {{A_T_runner_mean}} |
| winner bar | {{A_T_winner_disp}} |
| runner-up bar | {{A_T_runner_disp}} |
| kind of bar | {{A_T_disp_type}} |
| SD-like vs SE-like (what the test uses) | {{A_T_disp_treatment}} |
| run count | {{A_T_n_runs}} |
| where the run count is stated | {{A_T_n_source}} |

Human against human on the double-annotated items: winner {{A_hh_winner_mean}}, runner-up
{{A_hh_runner_mean}}, run count {{A_hh_n_runs}}, bar kind {{A_hh_disp_type}}, verdict {{A_hh_verdict}}.

Bar-less stratum ({{A_nobar_items}} items): no error bar printed for either cell, as the parser
said, in {{A_B_no_bar}}.

## Welch's t from the human-read values

Of the testable-stratum items, {{A_T_human_testable}} can be tested from what the human read
(both bars and a run count, or bars stated as SE or CI). Of those, {{A_T_not_separable}} are not
separable from the reported evidence at the stated run count. On the same items the parser's values
give {{A_T_parser_not_separable_same}}, and the two verdicts agree on {{A_T_verdict_agree}}.
In {{A_T_bold_not_best}} items the bold cell was not strictly the best printed value.

"Not separable from the reported evidence" means that the printed means, bars and run count do not
distinguish the two methods at the 5% level under the paper's stated conventions (unlabelled bars
read as standard deviations; Welch's t with Satterthwaite degrees of freedom). **It does not mean
that the claimed superiority is false.** The method may well be better; the table does not show it.
We make no claim of false superiority anywhere, and these counts are not an upper or lower bound
on any corpus rate: the reference strata were sampled on purpose and are reported separately.

## Page-level detection on random caption pages

On {{B_pages}} pilot caption pages drawn at random (seeded; each from a different paper), the
annotator listed every results-table group with exactly one bold cell that is strictly the best:
{{B_groups}} groups, and {{B_zero_pages}} pages with none. The parser lists {{B_recall_parser}} of
those groups (recall on this frame), and {{B_precision_parser}} of the parser's groups on these
pages are groups the person also lists (precision). For the census reader: recall
{{B_recall_census_reader}}, precision {{B_precision_census_reader}}. Missed groups, for example:
{{B_fn_examples}}. These figures hold for caption pages only. On {{B_nc_pages}} random pages where the
parser detected no caption, the annotator found {{B_nc_groups}} eligible groups.

## Targeted checks (deliberately selected hard cases; not accuracy samples)

- Pages the census reader listed as empty: the person found a single-winner group on
  {{C1_pilot_empty}} of the pages where the two readers disagree, and on {{C1_orientation_none}}
  of the random no-single-winner pages.
- Rate papers' evaluation protocol (human review of the model's reading, model values visible):
  the human confirmed the model's K on {{C2_K}}.
- The disputed run counts: decided from the full PDF for {{C3_decided}} items; the human agrees
  with the parser on {{C3_parser}}, with reader 1 on {{C3_reader1}}, with reader 2 on {{C3_reader2}}.
- Random papers with unlabelled or disputed bar kinds ({{C4_tables}}): the paper states SE or CI
  in {{C4_se_or_ci}}, and nothing at all in {{C4_not_stated}} tables. Applying the human bar kind to
  the parser's values changes the verdicts as follows: {{C4_flips}}.

## Per reviewer

- ezD2: [state the concern from the review] -> [the section above that answers it]
- U5Ta: [state the concern from the review] -> [the section above that answers it]
- LZY6: [state the concern from the review] -> [the section above that answers it]

## Changes to the paper

[To be written after the numbers above exist: which sentences change, which table gains a
human row, and whether any headline number moves.]
