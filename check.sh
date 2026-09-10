#!/bin/sh
# The paper's gate. Run before every commit that touches the submission.
#
# --allow lists numeric literals that are legitimately hand-written: 82.4 and
# 0.3 appear only in an illustrative example of what an unlabelled error bar
# looks like, not as findings. Everything else must be a registry macro.
exec python -m paperengine.cli check \
  --dir paper/submission --main main.tex \
  --allow "82.4,0.3" "$@"
