"""Build paper/aamas/supplementary.zip for OpenReview: the supplement PDF,
the run records every number comes from, the audit labels, and a README that
points to the code release. Kept well under the 25 MB limit; the rendered
audit images live in the code release."""
import os
import zipfile

FILES = [
    ("paper/aamas/supplement.pdf", "supplement.pdf"),
    ("paper/aamas/numbers.tex", "numbers.tex"),
    ("out/aamas/extra.json", "run_records/extra.json"),
    ("out/aamas/analysis.json", "run_records/analysis.json"),
    ("out/aamas/gold_set.json", "run_records/gold_set.json"),
    ("out/aamas/gold_set_pages.json", "run_records/gold_set_pages.json"),
    ("out/aamas/protocol.json", "run_records/protocol.json"),
    ("out/aamas/protocol_reader.json", "run_records/protocol_reader.json"),
    ("out/aamas/protocol_resolution_rows.json", "run_records/protocol_resolution_rows.json"),
    ("out/aamas/communities.csv", "run_records/communities.csv"),
    ("audits/aamas_gold/items.json", "audits/reference_set_items.json"),
    ("audits/aamas_gold/labels.csv", "audits/reference_set_reader_labels.csv"),
    ("audits/aamas_pages/items.json", "audits/random_pages_items.json"),
    ("audits/aamas_pages/labels.json", "audits/random_pages_reader_labels.json"),
    ("audits/aamas_comm_check/labels_sonnet.json", "audits/community_second_labeller.json"),
]
README = """Supplementary material for "Bold Without Bars: What Three Years of AAMAS Tables Let a Reader Check"

supplement.pdf        the supplementary text: reader protocols verbatim, classifier prompt,
                      per-paper protocol table, every scoring of the reference set, and the
                      list of reference items where reader and parser disagree
numbers.tex           every number in the paper as a LaTeX macro, generated from the run records
run_records/          the run records the macros are built from, including the per-comparison
                      database (analysis.json), the evaluation-protocol readings, the community labels
audits/               the reference-set and random-page items with the readers' labels

The full code release (the frozen parser, the AAMAS scripts, the extraction file, and the
rendered audit images) is at the anonymous repository named in the paper's Reproducibility
statement; run_all_aamas.sh there regenerates every number without network access.
"""


def main():
    out = "paper/aamas/supplementary.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", README)
        for src, dst in FILES:
            if os.path.exists(src):
                z.write(src, dst)
            else:
                print("missing", src)
    print(out, round(os.path.getsize(out) / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
