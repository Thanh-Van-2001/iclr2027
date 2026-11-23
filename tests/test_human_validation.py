"""Tests of the AAMAS human-validation scorer and kits on synthetic annotations.

No PDF, no network, no real human labels: every label below is invented for
the test and lives in a temporary directory. The repository-level tests at the
end check the committed kits (reproducible draws, no machine field in any
annotator-facing file, every shipped image present).
"""
from __future__ import annotations

import csv
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "aamas"))
sys.path.insert(0, os.path.join(ROOT, "study"))
sys.path.insert(0, ROOT)

import human_validation_score as hv  # noqa: E402
from analyze import test_comparison as welch  # noqa: E402

A_HEAD = ["id", "annotator_id", "kit", "kit_version"] + hv.A_COLS + ["complete", "first_opened_at", "last_saved_at", "seconds_on_item"]
B_HEAD = ["row_type", "page_id", "annotator_id", "kit", "kit_version", "page_status", "page_note", "table_key", "table_ref",
          "table_caption", "results_table", "orientation", "bold_rule", "group_key", "group_table_key", "group_label",
          "winner_value", "bold_is_best", "x_px", "y_px", "group_note", "complete", "first_opened_at", "last_saved_at",
          "seconds_on_page"]
C3_HEAD = ["id", "annotator_id", "kit", "kit_version"] + hv.C3_COLS + ["complete"]


def write_csv(path, head, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=head, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in head})


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)


def parser(**kw):
    base = {"winner": None, "winner_dispersion": None, "runner_up": None, "runner_dispersion": None,
            "direction": "higher_better", "orientation": "column", "dispersion_kind": "std", "n_runs": None,
            "n_runs_source": None, "winner_style": "pm", "runner_style": "pm"}
    base.update(kw)
    return base


def reader(**kw):
    base = {c: "" for c in ("results_table", "bold_ok", "orientation", "direction", "winner_mean", "winner_disp",
                            "runner_mean", "runner_disp", "disp_type", "n_runs", "n_source", "rival_copied",
                            "error_bar_present", "note", "cause")}
    base.update(kw)
    return base


def a_row(iid, ann="H1", **kw):
    base = {"id": iid, "annotator_id": ann, "kit": "comparison_blind", "kit_version": "aamas-hv-1",
            "target_visible": "y", "results_table": "y", "bold_unique": "y", "orientation": "column",
            "direction": "higher", "winner_bar": "present", "runner_bar": "present", "rival_copied": "n",
            "disp_source": "caption", "n_source": "caption", "paper_opened": "y", "evidence": "p.6 caption",
            "confidence": "high"}
    base.update(kw)
    return base


@pytest.fixture
def kit(tmp_path):
    """A synthetic kit directory: three comparison items, three pages, one run-count item."""
    d = tmp_path / "human_aamas"
    keys = d / "machine_keys"
    # B001: testable; parser read SD, n=3. B002: bar-less. B003: testable, parser read n=5 from the page.
    write_json(str(keys / "comparison_key.json"), {"items": {
        "B001": {"orig_id": "001", "stratum": "testable", "paper": "pA", "table": "2", "page": 5, "boxed": True,
                 "in_core": True, "in_overlap": True,
                 "parser": parser(winner=3558.0, winner_dispersion=40.0, runner_up=3533.0, runner_dispersion=39.0,
                                  dispersion_kind="unknown", n_runs=3, n_runs_source="caption"),
                 "reader1": reader(results_table="y", bold_ok="y", orientation="column", direction="higher",
                                   winner_mean="3558", winner_disp="40", runner_mean="3533", runner_disp="39",
                                   disp_type="unlabelled", n_runs="3", n_source="caption"),
                 "reader2": reader(results_table="y", bold_ok="y", orientation="column", direction="higher",
                                   winner_mean="3558", winner_disp="40", runner_mean="3533", runner_disp="39",
                                   disp_type="unlabelled", n_runs="5", n_source="paper")},
        "B002": {"orig_id": "101", "stratum": "no_bar", "paper": "pB", "table": "1", "page": 3, "boxed": True,
                 "in_core": True, "in_overlap": True,
                 "parser": parser(winner=0.91, runner_up=0.88, dispersion_kind="none", n_runs=None),
                 "reader1": reader(results_table="y", bold_ok="y", winner_mean="0.91", runner_mean="0.88", direction="higher"),
                 "reader2": reader(results_table="y", bold_ok="y", winner_mean="0.91", runner_mean="0.88", direction="higher")},
        "B003": {"orig_id": "002", "stratum": "testable", "paper": "pC", "table": "3", "page": 7, "boxed": True,
                 "in_core": True, "in_overlap": False,
                 "parser": parser(winner=11.0, winner_dispersion=1.0, runner_up=9.0, runner_dispersion=1.0,
                                  dispersion_kind="std", n_runs=5, n_runs_source="page"),
                 "reader1": reader(results_table="y", bold_ok="y", winner_mean="11.0", winner_disp="1.0",
                                   runner_mean="9.0", runner_disp="1.0", disp_type="sd", n_runs="5", n_source="page"),
                 "reader2": reader(results_table="y", bold_ok="y", winner_mean="11.0", winner_disp="1.0",
                                   runner_mean="9.0", runner_disp="1.0", disp_type="sd", n_runs="5", n_source="page")},
    }})
    write_json(str(keys / "page_key.json"), {"pages": {
        "P01": {"frame": "caption_pilot", "paper": "pA", "page": 5, "zoom": 2.0, "caption_pages_in_paper": 2,
                "parser": [{"table": "2", "winner": 3558.0, "winner_cell": {"x": 300.0, "y": 200.0}},
                           {"table": "2", "winner": 77.0, "winner_cell": {"x": 300.0, "y": 260.0}}],
                "census_reader": {"in_census_frame": True, "census_id": "0001", "tables": [
                    {"caption_start": "Table 2", "results_table": "y", "groups": [
                        {"label": "Hopper", "direction": "higher", "winner_mean": "3558", "runner_mean": "3533"}]}]},
                "pilot_reader": {"tables": []}},
        "P02": {"frame": "caption_pilot", "paper": "pD", "page": 2, "zoom": 2.0, "caption_pages_in_paper": 1,
                "parser": [{"table": "1", "winner": 5.0, "winner_cell": {"x": 100.0, "y": 100.0}}],
                "census_reader": {"in_census_frame": False, "census_id": None, "tables": None},
                "pilot_reader": {"tables": []}},
        "P03": {"frame": "noncaption", "paper": "pE", "page": 4, "zoom": 2.0, "caption_pages_in_paper": 3,
                "parser": [], "census_reader": {"in_census_frame": False, "census_id": None, "tables": None},
                "noncaption_reader": {"tables": []}},
    }})
    write_json(str(keys / "runcount_key.json"), {"items": {
        "R01": {"orig_id": "001", "paper": "pA", "table": "2", "page": 5, "disputed_by": ["reader1_vs_reader2"],
                "parser": {"n_runs": 3, "n_runs_source": "caption"},
                "reader1": {"n_runs": "3", "n_source": "caption", "note": ""},
                "reader2": {"n_runs": "5", "n_source": "paper", "note": ""}}}})
    write_json(str(d / "runcount_disputes" / "items.json"), [{"id": "R01", "pdf_url": "https://example.invalid/p.pdf#page=6"}])
    write_csv(str(d / "annotators.csv"), ["annotator_id", "kit", "role", "seen_machine_outputs", "notes"], [
        {"annotator_id": "H1", "kit": "comparison_blind", "role": "primary", "seen_machine_outputs": "n"},
        {"annotator_id": "H2", "kit": "comparison_blind", "role": "second", "seen_machine_outputs": "n"},
        {"annotator_id": "H1", "kit": "page_detection", "role": "primary", "seen_machine_outputs": "n"},
        {"annotator_id": "H1", "kit": "runcount_disputes", "role": "primary", "seen_machine_outputs": "n"}])
    return d


def run(kit, tmp_path):
    return hv.run(str(kit), str(tmp_path / "out"))


def rows_for(S, comparison, stratum, field):
    return [r for r in S["A_comparison_blind"]["_agree_rows"]
            if r["comparison"] == comparison and r["stratum"] == stratum and r["field"] == field]


# ----------------------------------------------------------------- parsing and statistics
@pytest.mark.parametrize("text,expected", [
    ("85.20", ("num", 85.2)), ("85.2%", ("num", 85.2)), ("−0.3", ("num", -0.3)), ("1,234.5", ("num", 1234.5)),
    ("1.2e-3", ("num", 0.0012)), ("85.2 ± 0.3", ("num", 85.2)), ("±0.3", ("num", 0.3)), ("(0.3)", ("num", 0.3)),
    ("[0.1;0.5]", ("num", 0.2)), ("none", ("none", None)), ("unclear", ("unclear", None)), ("", ("missing", None)),
    ("abc", ("bad", None)),
])
def test_parse_value(text, expected):
    st, v = hv.parse_value(text)
    assert st == expected[0]
    if expected[1] is not None:
        assert v == pytest.approx(expected[1])


def test_zero_denominator_is_na_not_a_percentage():
    r = hv.rate(0, 0)
    assert r["pct"] is None and r["text"].startswith("N/A")


def test_no_labels_everything_na(kit, tmp_path):
    S = run(kit, tmp_path)
    assert not S["human_labels_present"]
    assert S["A_comparison_blind"]["status"] == "no_human_labels"
    assert S["B_page_detection"]["status"] == "no_human_labels"
    rep = open(tmp_path / "out" / "report.md", encoding="utf-8").read()
    assert "No human labels yet" in rep


# ----------------------------------------------------------------- A: comparisons
def test_welch_recomputed_from_human_values_matches_the_paper_test(kit, tmp_path):
    write_csv(str(kit / "comparison_blind" / "raw" / "H1.csv"), A_HEAD, [
        a_row("B001", winner_mean="3558", winner_disp="40", runner_mean="3533", runner_disp="39",
              disp_type="unlabelled", n_runs="3")])
    S = run(kit, tmp_path)
    v = next(r for r in S["A_comparison_blind"]["_verdict_rows"] if r["id"] == "B001")
    ref = welch({"gap": 25.0, "winner_dispersion": 40.0, "runner_dispersion": 39.0,
                           "dispersion_kind": "unknown", "n_runs": 3})
    assert v["human_p"] == pytest.approx(ref["p"], abs=1e-6)
    assert v["human_p"] == pytest.approx(0.4815810517026551, abs=1e-6)   # the frozen pipeline_test of reference item 001
    assert v["human_verdict"] == "not_separable" and v["parser_verdict"] == "not_separable"
    assert v["human_agrees_with_parser"] == "y"


def test_missing_and_unclear_are_excluded_never_filled_from_a_machine(kit, tmp_path):
    write_csv(str(kit / "comparison_blind" / "raw" / "H1.csv"), A_HEAD, [
        a_row("B001", winner_mean="unclear", winner_disp="40", runner_mean="", runner_disp="39",
              disp_type="unclear", n_runs="", n_source="")])
    S = run(kit, tmp_path)
    A = S["A_comparison_blind"]
    wm = rows_for(S, "human_vs_parser", "testable", "winner_mean")[0]
    assert wm["n"] == 0 and wm["excluded"].get("unclear") == 1
    rm = rows_for(S, "human_vs_parser", "testable", "runner_mean")[0]
    assert rm["n"] == 0 and rm["excluded"].get("missing") == 1
    nr = rows_for(S, "human_vs_parser", "testable", "n_runs")[0]
    assert nr["n"] == 0
    assert A["coverage"]["unclear_answers_by_field"]["winner_mean"] == 1
    v = next(r for r in A["_verdict_rows"] if r["id"] == "B001")
    assert v["human_category"] in ("missing_answers", "value_unreadable") and v["human_p"] == ""


def test_wrong_bar_type_is_a_field_disagreement_and_changes_the_verdict(kit, tmp_path):
    # the human finds the bars are standard errors; the parser read them as deviations over 5 runs
    write_csv(str(kit / "comparison_blind" / "raw" / "H1.csv"), A_HEAD, [
        a_row("B003", winner_mean="11.0", winner_disp="1.0", runner_mean="9.0", runner_disp="1.0",
              disp_type="se", n_runs="5", n_source="page")])
    S = run(kit, tmp_path)
    dt = rows_for(S, "human_vs_parser", "testable", "disp_type")[0]
    assert (dt["k"], dt["n"]) == (0, 1)
    tr = rows_for(S, "human_vs_parser", "testable", "disp_treatment")[0]
    assert (tr["k"], tr["n"]) == (0, 1)
    v = next(r for r in S["A_comparison_blind"]["_verdict_rows"] if r["id"] == "B003")
    assert v["parser_verdict"] == "separable"        # SD 1.0 over 5 runs: SE 0.447 per arm, t = 3.16 on 8 df
    assert v["human_verdict"] == "not_separable"     # SE 1.0 per arm: t = 1.41 on 8 df
    p_sd = welch({"gap": 2.0, "winner_dispersion": 1.0, "runner_dispersion": 1.0, "dispersion_kind": "std", "n_runs": 5})
    assert (p_sd["p"] < 0.05) == (v["parser_verdict"] == "separable")
    dis = list(csv.DictReader(open(tmp_path / "out" / "disagreements.csv", encoding="utf-8")))
    assert any(r["field"] == "disp_type" and r["item"] == "B003" and r["other"] == "parser" for r in dis)


def test_conflicting_run_counts_are_counted_explicitly(kit, tmp_path):
    write_csv(str(kit / "comparison_blind" / "raw" / "H1.csv"), A_HEAD, [
        a_row("B001", winner_mean="3558", winner_disp="40", runner_mean="3533", runner_disp="39",
              disp_type="unlabelled", n_runs="5", n_runs_other="3 (caption); 8 evaluation episodes", n_source="ambiguous")])
    S = run(kit, tmp_path)
    A = S["A_comparison_blind"]
    assert A["coverage"]["run_count_ambiguous_or_conflicting"] == 1
    p = rows_for(S, "human_vs_parser", "testable", "n_runs")[0]
    r2 = rows_for(S, "human_vs_reader2", "testable", "n_runs")[0]
    assert (p["k"], p["n"]) == (0, 1) and (r2["k"], r2["n"]) == (1, 1)
    src = rows_for(S, "human_vs_parser", "testable", "n_source")[0]
    assert src["k"] == 0     # "ambiguous" never agrees with a single machine source


def test_bar_less_stratum_and_strata_reported_apart(kit, tmp_path):
    write_csv(str(kit / "comparison_blind" / "raw" / "H1.csv"), A_HEAD, [
        a_row("B002", winner_mean="0.91", runner_mean="0.88", winner_bar="absent", runner_bar="absent",
              disp_type="absent", disp_source="not_applicable", n_runs="none", n_source="absent"),
        a_row("B003", winner_mean="11.0", winner_disp="1.0", runner_mean="9.0", runner_disp="1.0",
              disp_type="sd", n_runs="5", n_source="page")])
    S = run(kit, tmp_path)
    nb = S["A_comparison_blind"]["by_stratum"]["no_bar"]
    assert nb["no_bar_on_either_side"]["k"] == 1 and nb["no_bar_on_either_side"]["n"] == 1
    assert S["A_comparison_blind"]["by_stratum"]["testable"]["labelled"] == 1


def test_void_item_without_a_box(kit, tmp_path):
    write_csv(str(kit / "comparison_blind" / "raw" / "H1.csv"), A_HEAD, [a_row("B001", target_visible="n")])
    S = run(kit, tmp_path)
    assert S["A_comparison_blind"]["coverage"]["void_no_box"] == 1
    assert rows_for(S, "human_vs_parser", "testable", "winner_mean")[0]["n"] == 0


def test_human_vs_human_on_the_overlap(kit, tmp_path):
    common = dict(winner_mean="3558", winner_disp="40", runner_mean="3533", runner_disp="39", disp_type="unlabelled")
    write_csv(str(kit / "comparison_blind" / "raw" / "H1.csv"), A_HEAD, [a_row("B001", n_runs="3", **common)])
    write_csv(str(kit / "comparison_blind" / "raw" / "H2.csv"), A_HEAD, [a_row("B001", ann="H2", n_runs="5", **common)])
    S = run(kit, tmp_path)
    hh = {r["field"]: r for r in S["A_comparison_blind"]["_agree_rows"] if r["comparison"] == "human_vs_human"}
    assert (hh["winner_mean"]["k"], hh["winner_mean"]["n"]) == (1, 1)
    assert (hh["n_runs"]["k"], hh["n_runs"]["n"]) == (0, 1)
    assert S["A_comparison_blind"]["human_vs_human"]["items_both"] == 1


def test_adjudication_is_separate_and_keeps_raw(kit, tmp_path):
    common = dict(winner_mean="3558", winner_disp="40", runner_mean="3533", runner_disp="39", disp_type="unlabelled")
    write_csv(str(kit / "comparison_blind" / "raw" / "H1.csv"), A_HEAD, [a_row("B001", n_runs="5", **common)])
    write_csv(str(kit / "comparison_blind" / "raw" / "H2.csv"), A_HEAD, [a_row("B001", ann="H2", n_runs="3", **common)])
    write_csv(str(kit / "comparison_blind" / "adjudication.csv"),
              ["id", "field", "annotator_a", "value_a", "annotator_b", "value_b", "adjudicated_value", "adjudicator", "rationale"],
              [{"id": "B001", "field": "n_runs", "annotator_a": "H1", "value_a": "5", "annotator_b": "H2", "value_b": "3",
                "adjudicated_value": "3", "adjudicator": "H3", "rationale": "caption says three trials"}])
    S = run(kit, tmp_path)
    raw = rows_for(S, "human_vs_parser", "testable", "n_runs")[0]
    adj = rows_for(S, "adjudicated_vs_parser", "testable", "n_runs")[0]
    assert (raw["k"], raw["n"]) == (0, 1)     # the raw answer is still what the primary row reports
    assert (adj["k"], adj["n"]) == (1, 1)


@pytest.mark.parametrize("rows,message", [
    ([a_row("B001"), a_row("B001")], "duplicate item id"),
    ([a_row("B999")], "unknown item id"),
    ([a_row("B001", orientation="diagonal")], "orientation"),
    ([a_row("B001", winner_mean="eighty")], "not a number"),
    ([a_row("B001"), a_row("B003", ann="H9")], "exactly one annotator_id"),
])
def test_schema_errors_fail_clearly(kit, tmp_path, rows, message):
    write_csv(str(kit / "comparison_blind" / "raw" / "H1.csv"), A_HEAD, rows)
    S = run(kit, tmp_path)
    assert any(message in e for e in S["errors"]), S["errors"]
    assert hv.main(["--kit-dir", str(kit), "--out", str(tmp_path / "out2")]) == 2


def test_missing_column_fails(kit, tmp_path):
    write_csv(str(kit / "comparison_blind" / "raw" / "H1.csv"), ["id", "annotator_id", "winner_mean"],
              [{"id": "B001", "annotator_id": "H1", "winner_mean": "1"}])
    S = run(kit, tmp_path)
    assert any("missing column" in e for e in S["errors"])


def test_raw_file_edited_after_freeze_is_refused(kit, tmp_path):
    path = kit / "comparison_blind" / "raw" / "H1.csv"
    write_csv(str(path), A_HEAD, [a_row("B001", winner_mean="3558")])
    write_json(str(kit / "comparison_blind" / "raw" / "FROZEN.json"),
               {"H1.csv": {"sha256": hv.sha256(str(path)), "frozen_at": "2026-11-23T00:00:00+00:00"}})
    assert not any("changed after" in e for e in run(kit, tmp_path)["errors"])
    write_csv(str(path), A_HEAD, [a_row("B001", winner_mean="3559")])
    assert any("changed after" in e for e in run(kit, tmp_path)["errors"])


def test_two_annotators_need_declared_roles(kit, tmp_path):
    os.remove(kit / "annotators.csv")
    write_csv(str(kit / "comparison_blind" / "raw" / "H1.csv"), A_HEAD, [a_row("B001")])
    write_csv(str(kit / "comparison_blind" / "raw" / "H2.csv"), A_HEAD, [a_row("B001", ann="H2")])
    S = run(kit, tmp_path)
    assert any("annotators.csv" in e for e in S["errors"])


def test_annotator_who_saw_machine_output_is_flagged_not_independent(kit, tmp_path):
    write_csv(str(kit / "annotators.csv"), ["annotator_id", "kit", "role", "seen_machine_outputs"],
              [{"annotator_id": "H1", "kit": "comparison_blind", "role": "primary", "seen_machine_outputs": "y"}])
    write_csv(str(kit / "comparison_blind" / "raw" / "H1.csv"), A_HEAD, [a_row("B001")])
    S = run(kit, tmp_path)
    assert any("NOT independent" in w for w in S["warnings"])


# ----------------------------------------------------------------- B: pages
def b_rows(pid, status, tables=(), groups=(), ann="H1", note=""):
    out = [{"row_type": "page", "page_id": pid, "annotator_id": ann, "kit": "page_detection", "page_status": status, "page_note": note}]
    for t in tables:
        out.append({"row_type": "table", "page_id": pid, "annotator_id": ann, "kit": "page_detection", **t})
    for g in groups:
        out.append({"row_type": "group", "page_id": pid, "annotator_id": ann, "kit": "page_detection", **g})
    return out


T2 = {"table_key": "t1", "table_ref": "Table 2", "results_table": "y", "orientation": "column", "bold_rule": "single_best"}


def test_page_with_no_eligible_groups_and_no_matching_table(kit, tmp_path):
    rows = (b_rows("P01", "groups_listed", [T2], [
                {"group_key": "g1", "group_table_key": "t1", "group_label": "Hopper", "winner_value": "3558",
                 "bold_is_best": "y", "x_px": "600", "y_px": "400"},
                # a group the parser does not have: a false negative
                {"group_key": "g2", "group_table_key": "t1", "group_label": "Walker", "winner_value": "4636",
                 "bold_is_best": "y", "x_px": "600", "y_px": "700"},
                # single bold but not the best: listed, not eligible
                {"group_key": "g3", "group_table_key": "t1", "group_label": "Ant", "winner_value": "12",
                 "bold_is_best": "n"}])
            + b_rows("P02", "none_found", note="only a figure")
            + b_rows("P03", "none_found", note="references"))
    write_csv(str(kit / "page_detection" / "raw" / "H1.csv"), B_HEAD, rows)
    S = run(kit, tmp_path)
    cap = S["B_page_detection"]["strata"]["caption_pilot"]
    par = cap["comparators"]["parser"]
    assert cap["human_eligible_groups"] == 2 and cap["pages_with_zero_eligible_groups"] == 1
    assert (par["recall"]["k"], par["recall"]["n"]) == (1, 2)
    # parser: 3558 matched; 77 on P01 and 5.0 on P02 (a page the human says has none) are false positives
    assert (par["precision"]["k"], par["precision"]["n"]) == (1, 3)
    assert {x["bold_value"] for x in par["false_negatives"]} == {"4636"}
    assert {x["page"] for x in par["false_positives"]} == {"P01", "P02"}
    cz = cap["comparators"]["census_reader"]
    assert (cz["recall"]["k"], cz["recall"]["n"]) == (1, 2) and cz["pages_outside_census_frame"] == 1
    assert cap["human_single_bold_groups_not_eligible"] == {"bold_is_best_n": 1}
    nc = S["B_page_detection"]["strata"]["noncaption"]
    assert nc["human_eligible_groups"] == 0 and nc["comparators"]["parser"]["recall"]["text"].startswith("N/A")


def test_value_match_prefers_the_clicked_cell():
    preds = [{"winner": 0.9, "winner_cell": {"x": 100.0, "y": 100.0}}, {"winner": 0.9, "winner_cell": {"x": 300.0, "y": 300.0}}]
    pair = hv.match_groups([{"winner": 0.9, "x": 600.0, "y": 600.0}], preds, zoom=2.0)
    assert pair == {0: 1}


def test_group_on_unlisted_table_is_a_schema_error(kit, tmp_path):
    rows = b_rows("P01", "groups_listed", [T2], [{"group_key": "g1", "group_table_key": "t9", "group_label": "x",
                                                  "winner_value": "1", "bold_is_best": "y"}])
    write_csv(str(kit / "page_detection" / "raw" / "H1.csv"), B_HEAD, rows)
    S = run(kit, tmp_path)
    assert any("unlisted table" in e for e in S["errors"])


def test_status_contradicting_groups_is_flagged(kit, tmp_path):
    rows = b_rows("P01", "none_found", [T2], [{"group_key": "g1", "group_table_key": "t1", "group_label": "x",
                                               "winner_value": "3558", "bold_is_best": "y"}])
    write_csv(str(kit / "page_detection" / "raw" / "H1.csv"), B_HEAD, rows)
    S = run(kit, tmp_path)
    assert any("none_found but 1 group" in w for w in S["warnings"])


# ----------------------------------------------------------------- C3
def test_runcount_dispute_decision(kit, tmp_path):
    write_csv(str(kit / "runcount_disputes" / "raw" / "H1.csv"), C3_HEAD, [
        {"id": "R01", "annotator_id": "H1", "kit": "runcount_disputes", "n_runs": "3", "n_unit": "seeds",
         "applies_to_table": "explicit", "n_source": "caption", "passage": "averaged over three experiment trials",
         "passage_location": "p.6 Table 2 caption", "confidence": "high"}])
    S = run(kit, tmp_path)
    C3 = S["C3_runcount_disputes"]
    assert C3["decided"] == 1 and C3["human_agrees_with"]["parser"]["k"] == 1
    assert C3["human_agrees_with"]["reader2"]["k"] == 0 and C3["passages_quoted"] == 1
    rows = list(csv.DictReader(open(tmp_path / "out" / "runcount_decisions.csv", encoding="utf-8")))
    assert rows[0]["human_agrees"] == "parser;reader1"


# ----------------------------------------------------------------- rebuttal template
def test_rebuttal_slots_stay_pending_without_labels():
    out = hv.fill_template("rate {{A_T_not_separable}} and {{B_recall_parser}}", {})
    assert out.count("[PENDING:") == 2


def test_every_template_slot_is_one_the_scorer_fills():
    import re
    text = open(os.path.join(ROOT, "audits", "human_aamas", "REBUTTAL_TEMPLATE.md"), encoding="utf-8").read()
    slots = set(re.findall(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}", text))
    assert slots and slots <= hv.TEMPLATE_SLOTS, sorted(slots - hv.TEMPLATE_SLOTS)


def test_filled_slots_come_only_from_human_data(kit, tmp_path):
    write_csv(str(kit / "comparison_blind" / "raw" / "H1.csv"), A_HEAD, [
        a_row("B001", winner_mean="3558", winner_disp="40", runner_mean="3533", runner_disp="39",
              disp_type="unlabelled", n_runs="3")])
    S = run(kit, tmp_path)
    vals = hv._slot_values(S)
    assert set(vals) <= hv.TEMPLATE_SLOTS
    assert vals["A_T_winner_mean"].startswith("1/1") and "B_recall_parser" not in vals


# ----------------------------------------------------------------- freeze and adjudication commands
@pytest.fixture
def kits_module(tmp_path, monkeypatch):
    import human_validation_kits as hk
    monkeypatch.setattr(hk, "ROOT", str(tmp_path))
    return hk


def test_freeze_records_hashes_and_refuses_an_edit(kits_module, tmp_path):
    raw = tmp_path / "audits" / "human_aamas" / "comparison_blind" / "raw"
    write_csv(str(raw / "H1.csv"), A_HEAD, [a_row("B001", winner_mean="1")])
    kits_module.freeze("comparison_blind")
    frozen = json.load(open(raw / "FROZEN.json", encoding="utf-8"))
    assert frozen["H1.csv"]["sha256"] == hv.sha256(str(raw / "H1.csv"))
    write_csv(str(raw / "H1.csv"), A_HEAD, [a_row("B001", winner_mean="2")])
    with pytest.raises(SystemExit, match="immutable"):
        kits_module.freeze("comparison_blind")


def test_adjudication_sheet_keeps_both_answers_and_never_overwrites(kits_module, tmp_path):
    raw = tmp_path / "audits" / "human_aamas" / "comparison_blind" / "raw"
    write_csv(str(raw / "H1.csv"), A_HEAD, [a_row("B001", n_runs="3", winner_mean="1")])
    write_csv(str(raw / "H2.csv"), A_HEAD, [a_row("B001", ann="H2", n_runs="5", winner_mean="1")])
    kits_module.adjudication_sheet("comparison_blind", "H1", "H2")
    path = tmp_path / "audits" / "human_aamas" / "comparison_blind" / "adjudication.csv"
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    assert [(r["field"], r["value_a"], r["value_b"], r["adjudicated_value"]) for r in rows] == [("n_runs", "3", "5", "")]
    with pytest.raises(SystemExit, match="never overwritten"):
        kits_module.adjudication_sheet("comparison_blind", "H1", "H2")


# ----------------------------------------------------------------- the committed kits
KIT = os.path.join(ROOT, "audits", "human_aamas")


@pytest.mark.skipif(not os.path.exists(os.path.join(KIT, "comparison_blind", "items.json")), reason="kits not built")
def test_committed_kits_have_no_machine_fields_and_all_images():
    import human_validation_kits as hk
    problems, report = hk.check(verbose=False)
    assert not problems, problems
    assert report["comparison_blind"]["with_shipped_image"] == 140
    assert report["page_detection"]["with_shipped_image"] == 50


def test_empty_pages_pack_hides_the_machine_reading(tmp_path):
    """C1: the sheet must not say which pages the readers disagreed on or called empty, and the
    pack must not carry items.json (it holds the census reader's note)."""
    import human_validation_kits as hk
    sheet = open(os.path.join(KIT, "empty_pages", "label.html"), encoding="utf-8").read().lower()
    assert not [t for t in hk.C1_FORBIDDEN if t in sheet]
    hk.pack("empty_pages", str(tmp_path))
    files = {os.path.relpath(os.path.join(b, f), tmp_path / "empty_pages").replace(os.sep, "/")
             for b, _, fs in os.walk(tmp_path / "empty_pages") for f in fs}
    assert "label.html" in files and "README_ANNOTATOR.txt" in files
    assert not any(f.endswith(".json") for f in files)
    assert sum(f.startswith("img_shipped/") for f in files) == 9
    assert (tmp_path / "empty_pages.zip").exists()


@pytest.mark.skipif(not os.path.exists(os.path.join(KIT, "machine_keys", "comparison_key.json")), reason="keys not built")
def test_draws_are_reproducible():
    import human_validation_kits as hk
    by_id, boxed, core_t, core_b, ov, optional, blind = hk._comparison_items({})
    key = json.load(open(os.path.join(KIT, "machine_keys", "comparison_key.json"), encoding="utf-8"))["items"]
    assert {bid: k["orig_id"] for bid, k in key.items()} == {b: o for o, b in blind.items()}
    assert (len(core_t), len(core_b), len(ov), len(optional)) == (70, 30, 30, 40)
    assert all(by_id[i].get("mark") for i in core_t + core_b)       # the core holds boxed items only
    union, pairs, *_ = hk.runcount_disputed_ids()
    assert len(union) == 18 and [len(pairs[k]) for k in ("reader1_vs_parser", "reader2_vs_parser", "reader1_vs_reader2")] == [15, 11, 9]
    pil, nc, draw, draw_nc, pov = hk._page_draw()
    pk = json.load(open(os.path.join(KIT, "machine_keys", "page_key.json"), encoding="utf-8"))["pages"]
    assert [pk[f"P{i:02d}"]["source_id"] for i in range(1, 31)] == draw
    assert [pk[f"P{i:02d}"]["source_id"] for i in range(31, 51)] == draw_nc


@pytest.mark.skipif(not os.path.exists(os.path.join(KIT, "paper_urls.json")), reason="no url map")
def test_paper_urls_hash_to_their_ids():
    import hashlib
    urls = json.load(open(os.path.join(KIT, "paper_urls.json"), encoding="utf-8"))
    assert len(urls) == 827
    assert all(hashlib.sha1(u["pdf"].encode()).hexdigest()[:16] == pid for pid, u in urls.items())
