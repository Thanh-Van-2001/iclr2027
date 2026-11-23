# Independent human validation for the AAMAS paper (submission 3154)

**Status: kits built and tested; no human label has been collected.** Every human number the
scorer prints is N/A until a person fills a kit. Nothing in this folder may be described as
human validation before the raw files in `*/raw/` exist.

Nothing here changes the frozen parser (`study/`), its run records, the reader labels
(`audits/aamas_gold/labels.csv`, `audits/aamas_gold_gemini/labels.csv`, the census labels), the
reference-set draw or any headline number. No language model is called. The paper's own
Vietnamese guide for the two earlier kits is `README_VI.md`.

## What was already here, and what is new

| | already in the repository | added on this branch |
|---|---|---|
| reference comparisons | 140 items with crops (`audits/aamas_gold`), two model readers' labels, `study/gold_set.py score` | **A.** `comparison_blind/`: a blind kit (no stratum, no machine value; blind ids), a seeded 100-item core and a seeded 30-item double-annotation subset |
| page level | 100 random pilot caption pages with renders and the first reader's labels (`audits/aamas_pages`); census labels; 100 non-caption pages with renders | **B.** `page_detection/`: 30 of the pilot pages and 20 non-caption pages, drawn at random, where a person lists every eligible group (or states there is none), clicking each bold cell |
| hard cases | `empty_pages/` (35 pages: 5 pilot pages the readers disagree on + 30 random no-single-winner pages) with a one-question sheet | **C1.** the sheet rebuilt (`python aamas/human_kits.py --html-only`) with annotator ID, autosave, resume, PDF links and an explicit image status (9 shipped pilot renders, 26 census renders not shipped) |
| protocol | `protocol_check.csv` (20 rate papers, model values pre-filled) | **C2.** `protocol_review/protocol_links.csv`: public PDF URLs; scored as a review/correction, not as blind truth |
| run counts | the two readers' and the parser's run counts on the reference items | **C3.** `runcount_disputes/`: the 18 items where they disagree, with crop, PDF link, search aid; the human quotes the passage |
| bar kinds | parser `dispersion_kind = unknown` on 27 tables; readers disagree on 3 | **C4.** `bartype_random/`: a seeded random order of those 19 papers, a 12-paper core; the human reads the whole PDF |
| scoring | `aamas/human_score.py` (C1, C2) | **D.** `aamas/human_validation_score.py`, `tests/test_human_validation.py`, `REBUTTAL_TEMPLATE.md` |
| links | none (PDFs are not shipped) | `paper_urls.json`: the public IFAAMAS URL of all 827 papers; each one checks offline, since `id = sha1(url)[:16]` |

Code: `aamas/human_validation_kits.py` (draws, keys, sheets, check, pack, freeze, adjudication
sheet), `aamas/human_kit_ui.py` (the two offline sheet types), `aamas/human_validation_score.py`.

## What can be reviewed now

| kit | items | image shipped in the repo | needs | output file the sheet exports |
|---|---|---|---|---|
| A `comparison_blind` | 140 (core 100, overlap 30) | 140 of 140 crops | internet for the full PDF (or `data/corpus`) | `comparison_blind_<ID>.csv` |
| B `page_detection` | 50 (30 caption + 20 non-caption) | 50 of 50 page renders | internet for the PDF when a page is unclear | `page_detection_<ID>.csv` |
| C1 `empty_pages` | 35 | 9 of 35 (shipped pilot renders) | the other 26: the PDF link, or `data/corpus` + `aamas/sample_all_caption_pages.py` | `empty_pages_labels.csv` (into `empty_pages/raw/`) |
| C2 `protocol_check.csv` | 20 papers | none needed | the PDF | the same CSV, human columns |
| C3 `runcount_disputes` | 18 | 18 of 18 crops | the PDF (the decision is from the whole paper) | `runcount_disputes_<ID>.csv` |
| C4 `bartype_random` | 30 tables / 19 papers (core 16 / 12) | none (by design) | the PDF | `bartype_random_<ID>.csv` |

`python aamas/human_validation_kits.py check` verifies all of this and exits 1 when an image or URL
is missing, or when an annotator-facing file mentions a machine field.

## Protocol

1. **Who.** An annotator must not have seen any machine reading of these items (the reference
   labels, `items.json` of `audits/aamas_gold`, the census labels, the paper's tables of results).
   Record every annotator in `annotators.csv` (`annotator_id, kit, role, seen_machine_outputs,
   notes`; role `primary`, `second` or `adjudicator`). Labels from someone who answers
   `seen_machine_outputs = y` are scored but reported as **not independent**.
2. **What they get.** Not the repository: a packed folder per kit,
   `python aamas/human_validation_kits.py pack --kit comparison_blind --out <dir>`
   (sheet, images, blank template, three-line instructions; the pack is refused if any file in it
   names a machine field). `--kit` is one of `comparison_blind`, `page_detection`, `runcount_disputes`,
   `bartype_random`, `empty_pages`; the C1 pack carries only the sheet and its 9 shipped renders, never
   `empty_pages/items.json`, which holds the census reading. They open `label.html` in a browser, enter their ID and work;
   answers autosave in the browser and survive a reload; *Resume from CSV* continues on another
   computer.
3. **Order.** A core first (`Core 100`), then B (`Set 1`), then C3/C4. The second annotator does
   `Double-annotation 30` of A (and `Double-annotation 8` of B), without contact with the first.
4. **Collect.** Put each exported CSV, unchanged, in `<kit>/raw/` (any file name ending in .csv;
   one file per annotator), then freeze it:
   `python aamas/human_validation_kits.py freeze --kit comparison_blind`.
   The scorer refuses a raw file whose hash changed after freezing.
5. **Adjudicate (optional).** `python aamas/human_validation_kits.py adjudication-sheet --kit
   comparison_blind --a H1 --b H2` writes `comparison_blind/adjudication.csv` with both original
   answers on every disagreeing field. A third person fills `adjudicated_value`, `adjudicator`,
   `rationale`. Raw files are never edited, and adjudicated values are reported only in their own rows.
6. **Score.** `python aamas/human_validation_score.py` writes `out/aamas/human_validation/`
   (`summary.json`, `agreement_by_field.csv`, `verdicts.csv`, `disagreements.csv`, `report.md`,
   `rebuttal_filled.md`, `runcount_decisions.csv`, `page_groups_matched.csv`). It exits 2 when a label
   file fails validation (missing column, duplicate or unknown id, a value outside the allowed set,
   two annotator ids in one file, an edited frozen file). `--require-labels` exits 1 when there are
   no human labels at all. The earlier scorer `python aamas/human_score.py` still reads C1 and C2.

## Commands

    pip install -r requirements.txt pytest
    python aamas/human_validation_kits.py check                 # images, URLs, leak scan
    python aamas/human_validation_kits.py pack --kit comparison_blind --out ../hv_packs
    python aamas/human_kits.py --html-only                      # rebuild the C1 sheet only
    python aamas/human_validation_kits.py html                  # rebuild the A, B, C3, C4 sheets only
    python aamas/human_validation_score.py                      # score whatever labels exist
    python -m pytest tests/test_human_validation.py -q

Rebuilding the draws and keys (deterministic; the committed files are the outcome, and
`tests/test_human_validation.py::test_draws_are_reproducible` checks they reproduce):

    python aamas/human_validation_kits.py build --analysis out/aamas/analysis.json

`out/aamas/analysis.json` is the frozen run record (released as `run_records/analysis.json`;
SHA-256 `af0e7106...b93d026`, recorded in the manifests). Without `--analysis` the build keeps the
existing page and bar-type keys and rewrites only what it can from the repository. It never runs
the parser and never re-renders a page from a PDF.

## Statistical conventions (the scorer's docstring has the full list)

- Field agreement is exact (numbers within a relative 1e-6), per field, per stratum, per machine
  (parser, reader 1, reader 2) and between humans; `unclear` and blank answers are excluded and counted,
  never replaced by a machine value.
- Welch's t is recomputed with the paper's own function (`study/analyze.py:test_comparison`) from the
  human-read means, bars, bar kind and run count. Unlabelled bars are read as SD, with a
  sensitivity reading them as SE. p >= 0.05 is reported as "not separable from the reported
  evidence", never as "false superiority".
- Wilson 95% intervals (descriptive) and 2000-resample percentile bootstraps over papers (A) or
  pages (B; each pilot page is a different paper), seed 0. Zero denominators print N/A.
- Page-level recall and precision hold for the pilot caption-page frame. A version weighted to all
  caption pages (weight = the paper's number of caption pages) is printed beside it; the non-caption
  stratum is reported separately.
- None of the targeted sets (C1, C3, C4, the reference strata) supports a corpus rate or a bound.

## Limitations

- No human label exists yet; all of the above is infrastructure.
- 26 of the 35 hard-case pages (C1) have no shipped image; the annotator uses the PDF link.
- The page draw (B) inherits the pilot's frame ("Table N:" caption pages, one page per paper);
  it says nothing about pages outside that frame except through the separate non-caption stratum.
- The "18 disputed run counts" are reconstructed from the shipped files by an explicit rule
  (`runcount_disputes/manifest.json`); the rule reproduces 15 + 11 + 9 pairwise disagreements and a
  union of exactly 18, but the reviews themselves are not in the repository to confirm the definition.
- The blind kit hides the stratum, but anyone with the repository can look it up; blinding rests on
  annotators receiving only the packed folder.
