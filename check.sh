#!/bin/sh
# The paper's gate. Run before every commit that touches the submission.
#
# --allow lists numeric literals that are legitimately hand-written. The list is
# kept short enough to justify line by line, because a long whitelist defeats
# the audit:
#
#   82.4, 0.3    an illustrative cell showing what an unlabelled error bar
#                looks like, in Section 7. Not a finding.
#   76.63, 3.98  the actual value that exposed the sixth parser bug, quoted in
#                Section 9 so the reader can see the format that broke. Not a
#                finding either, and quoting it approximately would be worse.
#   221          a corpus size from Christodoulou et al., quoted in related
#                work. Not our measurement, and checkable by the reader through
#                the citation next to it.
#
# Every other number in the paper is a macro generated from a run record.
exec python -m paperengine.cli check \
  --dir paper/submission --main main.tex \
  --allow "82.4,0.3,76.63,3.98,221" "$@"
