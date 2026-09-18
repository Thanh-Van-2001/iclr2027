# Model runs behind the metaheuristics paper

Every model reading names its model in the `draw.json` (or `*_set.json`) beside its labels:

| reading | model | record |
|---|---|---|
| kind classifier (1644 papers) | gemini/gemini-3.1-pro-preview via relay | out/swevo/kinds_shard*.csv, out/swevo/kinds_models.json |
| second kind labeller (100) | cc/claude-sonnet-5 via relay | out/swevo/kinds_second_sonnet.csv |
| reader census (2320 pages) | gemini/gemini-3.1-pro-preview | audits/swevo_census/labels*.json, draw.json |
| Mean/Std-row re-reads (236 + 135 pages) | gemini/gemini-3.1-pro-preview | audits/swevo_census_rows*/labels*.json, instruction.txt, draw.json |
| printed-verdict reading (179 pages) | gemini/gemini-3.1-pro-preview | audits/swevo_verdict/labels*.json, draw.json |
| reference set (140 items), two readers | gemini/gemini-3.1-pro-preview; cc/claude-sonnet-5 | audits/swevo_gold/labels_gemini.csv, labels_sonnet.csv, draw.json |
| full-text reading (361 papers), two windows | gemini/gemini-3.1-pro-preview | out/swevo/test_reader_part*.json (80k chars), test_reader_v2_part*.json (400k), test_reader_set.json |
| second full-text reader (100) | cc/claude-sonnet-5 | out/swevo/test_reader_second*.json, test_reader_second_set.json |

The relay is an OpenAI-compatible endpoint named by `RELAY_URL`; the model ids are the relay's, dated by the runs
(September 2026). Reasoning effort is the relay's default unless a record says `low`.
