"""Regression tests for every extractor bug the audits found.

Each test is a table pattern that once produced a confident and wrong number.
They run on synthetic spans, so they need no PDF and no network.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "study"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import analyze  # noqa: E402
import extract  # noqa: E402


def _span(text, x, y, *, h=8.0, bold=False, page=0):
    return {"text": text, "bold": bold, "page": page, "y": y, "x": x,
            "x1": x + 4.0 * len(text), "y1": y + h, "size": h}


def _cells(lines):
    return [c.to_dict() for c in extract._cells_from_lines(lines)]


def test_subscript_error_bar_stays_with_its_mean():
    # Bug 1: a subscript bar sits lower than its baseline and was paired with
    # the neighbouring column's mean.
    spans = [_span("91.48", 100, 100), _span("±0.40", 122, 103, h=5),
             _span("66.53", 200, 100), _span("±8.55", 222, 103, h=5)]
    cells = _cells(extract._lines(spans))
    got = {(c["mean"], c["dispersion"]) for c in cells}
    assert (91.48, 0.40) in got and (66.53, 8.55) in got


def test_tall_row_label_does_not_merge_two_rows():
    # Bug 7: a label spanning two six-point rows widened the line, and the
    # second row was glued onto the first: 0.67 and 0.00 became 670.0.
    spans = [_span("10", 50, 100, h=13),
             _span("0.67", 100, 100, h=6, bold=True), _span("±", 118, 100, h=6), _span("0.29", 124, 100, h=6),
             _span("0.00", 100, 106.6, h=6), _span("±", 118, 106.6, h=6), _span("0.00", 124, 106.6, h=6)]
    cells = _cells(extract._lines(spans))
    means = sorted(c["mean"] for c in cells if c["dispersion"] is not None)
    assert means == [0.0, 0.67]


def test_unmarked_glyph_gap_splits_a_row_span():
    # Bug 8: a whole row set as one span without space characters read as
    # 0.7015±0.00070.2577±0.0046, and the parser found a winner of 2577.
    def ch(c, x, w=4.0):
        return {"c": c, "bbox": (x, 100.0, x + w, 108.0)}
    chars = []
    x = 0.0
    for tok in ("0.7015", "±", "0.0007"):
        for c in tok:
            chars.append(ch(c, x)); x += 4.0
    x += 12.0
    for tok in ("0.2577", "±", "0.0046"):
        for c in tok:
            chars.append(ch(c, x)); x += 4.0
    pieces = extract._split_span(chars, 8.0)
    assert [p[0] for p in pieces] == ["0.7015±0.0007", "0.2577±0.0046"]


def test_run_count_reads_words_and_ignores_task_names():
    # Bug 9: "four seeds" was invisible and "Walker Run" beneath a 95 read as
    # 95 runs.
    assert extract._n_runs("averaged over four random seeds", "") == (4, "caption")
    assert extract._n_runs("", "we perform ten runs of cross-validation") == (10, "page")
    assert extract._n_runs("", "273.00 ± 61.73\nRun 437.49") == (None, None)
    assert extract._n_runs("", "over 3 random runs; Walker Run 1.0")[0] == 3


def test_caption_kind_beats_page_kind_and_paper_is_last_resort():
    assert extract._dispersion_kind("mean with standard deviation",
                                    "Table 1 reports the standard error", "") == "std"
    assert extract._dispersion_kind("Table 1: accuracy", "",
                                    "We report the mean and standard deviation") == "std"
    assert extract._dispersion_kind("Table 1: accuracy", "",
                                    "standard deviation here, 95% CI there") == "unknown"


def _cell(mean, x, y, *, bold=False, disp=None, text=None):
    return {"text": text or (f"{mean}" if disp is None else f"{mean} ± {disp}"),
            "mean": mean, "dispersion": disp, "dispersion_style": "pm" if disp else "none",
            "bold": bold, "page": 0, "y": y, "x": x}


def test_block_structured_columns_keep_column_orientation():
    # Bug 10: one bold per dataset block made every column multi-bold, the
    # vote flipped to rows, and a method's MCE was compared with its ECE.
    cells = []
    for b, y0 in enumerate((100, 160)):          # two blocks, three rows each
        for r in range(3):
            y = y0 + 12 * r
            cells.append(_cell(1.0 + r + 10 * b, 100, y, bold=(r == 0), disp=0.1))
            cells.append(_cell(5.0 + r + 10 * b, 200, y, bold=(r == 2), disp=0.1))
    assert analyze.orientation(cells) == "column"
    cmps = analyze.comparisons_from_table({"cells": cells, "number": "1", "page": 0,
                                           "dispersion_kind": "std", "n_runs": 3, "caption": ""})
    assert len(cmps) == 4
    assert all(c["gap"] < 5 for c in cmps)


def test_irregular_bold_columns_are_not_split():
    # A method that wins some tasks and not others proposes cuts nobody else
    # does; the table keeps row orientation.
    cells = []
    winners = [0, 0, 1, 0, 2, 0, 1, 0]
    for r in range(8):
        y = 100 + 12 * r
        for k in range(3):
            cells.append(_cell(10 + k + (5 if winners[r] == k else 0), 100 + 80 * k, y,
                               bold=(winners[r] == k), disp=0.5))
    assert analyze.orientation(cells) == "row"


def test_bare_integer_row_labels_are_not_values():
    # Bug 11: "# demos = 10" in the first column outranked the bold 0.67.
    cells = [_cell(10, 40, 100, text="10"), _cell(0.17, 100, 100, disp=0.09),
             _cell(0.57, 150, 100, disp=0.21), _cell(0.67, 200, 100, bold=True, disp=0.29)]
    cells += [_cell(20, 40, 112, text="20"), _cell(0.10, 100, 112, disp=0.09),
              _cell(0.74, 150, 112, disp=0.08), _cell(0.72, 200, 112, bold=True, disp=0.05)]
    cmps = analyze.comparisons_from_table({"cells": cells, "number": "1", "page": 0,
                                           "dispersion_kind": "std", "n_runs": 5, "caption": ""})
    assert any(c["winner"] == 0.67 and c["runner_up"] == 0.57 for c in cmps)
    assert all(c["winner"] < 5 for c in cmps)


def test_top_three_captions_are_discarded():
    cells = [_cell(1.0, 100, 100, bold=True, disp=0.1), _cell(0.9, 100, 112, disp=0.1),
             _cell(0.8, 100, 124, disp=0.1)]
    table = {"cells": cells, "number": "1", "page": 0, "dispersion_kind": "std", "n_runs": 3}
    assert analyze.comparisons_from_table(dict(table, caption="best in bold")) != []
    assert analyze.comparisons_from_table(
        dict(table, caption="First, second and third best results are colour-coded")) == []


def test_zero_error_bar_is_an_error_bar():
    assert analyze._standard_error(0.0, "std", 3) == 0.0
    assert analyze.test_comparison({"gap": 1.0, "winner_dispersion": 0.0, "runner_dispersion": 0.5,
                                    "dispersion_kind": "std", "n_runs": 3}) is not None
    assert analyze.test_comparison({"gap": 1.0, "winner_dispersion": 0.0, "runner_dispersion": 0.0,
                                    "dispersion_kind": "std", "n_runs": 3}) is None


def test_dispersion_without_leading_zero():
    # Bug 12: 0.444 +/- .003 was read as a bare 0.444; a whole table of them was
    # called empty by the recall audit.
    spans = [_span("0.444", 100, 100), _span("±.003", 122, 103, h=5),
             _span("0.643", 200, 100), _span("(.004)", 224, 100)]
    cells = _cells(extract._lines(spans))
    got = {(c["mean"], c["dispersion"]) for c in cells}
    assert (0.444, 0.003) in got and (0.643, 0.004) in got


def test_bold_weight_recognised_by_font_name():
    # Bug 13: Nimbus Roman's bold face is "-Medi" and the flag bit was unset.
    assert extract._bold_by_name("NimbusRomNo9L-Medi")
    assert extract._bold_by_name("CMBX10")
    assert extract._bold_by_name("TimesNewRomanPS-BoldMT")
    assert not extract._bold_by_name("NimbusRomNo9L-Regu")
    assert not extract._bold_by_name("CMR10")


def test_rank_in_parentheses_is_not_a_bar_and_ties_claim_nothing():
    cells = [_cell(0.9984, 100, 100, bold=True, disp=1.0, text="0.9984 (1)"),
             _cell(0.9845, 100, 112, disp=2.0, text="0.9845 (2)"),
             _cell(0.9700, 100, 124, disp=3.0, text="0.9700 (3)")]
    for c in cells:
        c["dispersion_style"] = "paren"
    cmps = analyze.comparisons_from_table({"cells": cells, "number": "1", "page": 0,
                                           "dispersion_kind": "std", "n_runs": 3, "caption": ""})
    assert len(cmps) == 1 and cmps[0]["winner_dispersion"] is None
    tie = [_cell(67.5, 100, 100, bold=True, disp=5.0), _cell(67.5, 100, 112, disp=5.0),
           _cell(60.0, 100, 124, disp=5.0)]
    assert analyze.comparisons_from_table({"cells": tie, "number": "1", "page": 0,
                                           "dispersion_kind": "std", "n_runs": 3, "caption": ""}) == []


def test_run_counts_in_other_phrasings():
    # Bug 15: the run-count audit found these phrasings in 18 of 40 papers
    # the pattern had called silent.
    assert extract._n_runs("", "each experiment is repeated five times, with results averaged")[0] == 5
    assert extract._n_runs("", "we repeat each experiment 10 times to reduce randomness")[0] == 10
    assert extract._n_runs("", "test accuracies over three randomly seeded runs")[0] == 3
    assert extract._n_runs("", "For Table 2, we average over seeds 32, 33, and 34")[0] == 3
    assert extract._n_runs("", "which is almost 10 times higher than the baseline") == (None, None)
