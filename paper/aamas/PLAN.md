# AAMAS 2027 paper — plan (started 2026-09-15)

Deadlines (AoE): OpenReview author registration 17 Sep; abstract 1 Oct; paper 8 Oct;
rebuttal 20–24 Nov; notification 21 Dec. Format: `aamas.cls` sigconf, anonymous,
8 pages main text + unlimited references; supplementary zip ≤ 25 MB (appendix PDF
+ code pointer). LLM policy: disclose tool, version and prompts wherever a model
did more than polish text (the VLM reader is disclosed in full).

## Question
What do AAMAS papers print beside a bold result, and can a reader check it?
Same instrument as the ICLR submission, frozen (`git tag frozen-v1`), pointed
at a different corpus with different questions.

## Corpus
IFAAMAS open proceedings, main track only: 2024 (230), 2025 (260), 2026 (337)
= 827 full papers; `data/extracted_aamas.jsonl`, PDFs cached in `data/corpus`.
Comparison corpus: NeurIPS/ICML 2024–25 (2895 papers, already extracted).

## Contributions (each needs a run record → macro)
1. Census: share of highlighted comparisons with no bar, testable share, failure
   rate at stated seeds (Welch, z, Holm), AAMAS vs NeurIPS/ICML under identical
   definitions; three-year trend inside AAMAS.
2. By community inside AAMAS: learning (RL/MARL) vs game theory & social choice
   vs LLM/agentic vs simulation vs other — classifier on title + first page
   (LLM via relay, prompt released), with a hand-checkable sample.
3. Evaluation-protocol resolution: win/success rates over K evaluation episodes
   × S seeds — binomial resolution at the stated K·S; share of highlighted
   win-rate gaps below it. Ties to Gorsane et al. 2022 recommendations.
4. Instrument on the two-column format: frozen pipeline, reference set drawn
   from AAMAS (100 testable + 40 no-bar), VLM reader (Claude Opus 5), precision
   and verdict agreement; random-page recall audit (smaller).
5. Release: pipeline commit, per-comparison database, renderings, labels.

## Steps
- [x] `aamas_index` source in harvest.py; pipeline running with PDF cache.
- [ ] Dedupe jsonl (two processes overlapped for the first ~45 papers).
- [ ] `aamas/make_all_aamas.py`: analyse + extra_stats + sensitivity on the AAMAS
      file; side-by-side with 2025 corpus; per-year; per-community.
- [ ] Episode-count extractor (`evaluat\w+ (over|on|for) (\d+) episodes`, `test episodes`)
      + binomial resolution per comparison whose metric is a rate.
- [ ] Community classifier via relay (Gemini 3.1 Pro), 827 titles + first page.
- [ ] Gold set: `gold_set.py sample --extracted data/extracted_aamas.jsonl
      --analysis out/aamas/analysis.json --source aamas2024/5/6 --seed 2027`
      → render → VLM read (workflow gold-d-vlm-read adapted) → score.
- [ ] Random-page audit (gold_f-style), ~100 pages.
- [ ] make_numbers for AAMAS → `paper/aamas/numbers.tex`; check.sh variant.
- [ ] Draft in `paper/aamas/main.tex`; 8 pages; reviews r1–r3; release repo.

## Literature to verify and cite (MAS-specific)
Gorsane et al. 2022 (NeurIPS) standardised MARL evaluation; Papoudakis et al.
2021 benchmarking MARL; Agarwal et al. 2021 rliable; Colas et al. 2018 seeds;
Henderson et al. 2018; Jordan et al. 2020; Patterson et al. 2023 empirical design
in RL; Samvelyan et al. 2019 SMAC; Ellis et al. 2023 SMACv2; Yu et al. 2022 MAPPO;
Hu et al. 2021 MARL tricks; Bettini et al. 2024 BenchMARL; Lowe et al. 2017;
Rashid et al. 2018 QMIX; plus the reporting literature already in refs.bib.
