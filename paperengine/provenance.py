"""Number provenance.

The rule this module enforces: **no number reaches the PDF unless it was
computed by a recorded run.**

Every experiment writes a :class:`RunRecord` to ``results/``.  Tables, figures
and inline statistics are then generated *from* those records, never typed.  A
final audit pass reads the LaTeX source and fails the build if it finds a
numeric literal that did not come from the registry.

This is what makes the difference between a paper an author can defend under
review and a paper whose numbers drifted out of a chat transcript.
"""

from __future__ import annotations

import argparse
import dataclasses
import glob
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from typing import Any, Iterable, Optional

RESULTS_DIR = os.environ.get(
    "PAPERENGINE_RESULTS",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results"),
)


def _git_revision() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10,
            cwd=os.path.dirname(RESULTS_DIR),
        )
        rev = out.stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, timeout=10,
            cwd=os.path.dirname(RESULTS_DIR),
        ).stdout.strip()
        return (rev or "unknown") + ("-dirty" if dirty else "")
    except (OSError, subprocess.SubprocessError):
        return "unknown"


# --------------------------------------------------------------------------
# run records
# --------------------------------------------------------------------------

@dataclasses.dataclass
class RunRecord:
    """One executed experiment.

    ``metrics`` maps a metric name to either a scalar or a list of per-seed
    values.  Lists are strongly preferred: a single-seed number is exactly the
    kind of result ICLR reviewers reject.
    """

    run_id: str
    experiment: str
    config: dict
    metrics: dict[str, Any]
    timestamp: str
    code_revision: str = dataclasses.field(default_factory=_git_revision)
    n_samples: Optional[int] = None
    notes: str = ""

    def content_hash(self) -> str:
        blob = json.dumps(
            {"experiment": self.experiment, "config": self.config, "metrics": self.metrics},
            sort_keys=True, default=str,
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["content_hash"] = self.content_hash()
        return d


def record_run(
    experiment: str,
    config: dict,
    metrics: dict[str, Any],
    *,
    timestamp: str,
    run_id: Optional[str] = None,
    n_samples: Optional[int] = None,
    notes: str = "",
    results_dir: str = RESULTS_DIR,
) -> RunRecord:
    """Persist one run.  ``timestamp`` is passed in so callers stay explicit."""
    os.makedirs(results_dir, exist_ok=True)
    rec = RunRecord(
        run_id=run_id or f"{experiment}-{hashlib.sha256((experiment + timestamp).encode()).hexdigest()[:8]}",
        experiment=experiment,
        config=config,
        metrics=metrics,
        timestamp=timestamp,
        n_samples=n_samples,
        notes=notes,
    )
    path = os.path.join(results_dir, f"{rec.run_id}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rec.to_dict(), fh, indent=2, default=str)
    return rec


def load_runs(results_dir: str = RESULTS_DIR, experiment: Optional[str] = None) -> list[RunRecord]:
    out: list[RunRecord] = []
    for path in sorted(glob.glob(os.path.join(results_dir, "*.json"))):
        with open(path, "r", encoding="utf-8") as fh:
            try:
                d = json.load(fh)
            except json.JSONDecodeError:
                continue
        d.pop("content_hash", None)
        try:
            rec = RunRecord(**d)
        except TypeError:
            continue
        if experiment is None or rec.experiment == experiment:
            out.append(rec)
    return out


# --------------------------------------------------------------------------
# aggregation
# --------------------------------------------------------------------------

@dataclasses.dataclass
class Estimate:
    """A number destined for the paper, with the uncertainty attached."""

    value: float
    lo: Optional[float] = None
    hi: Optional[float] = None
    n: Optional[int] = None
    source_runs: list[str] = dataclasses.field(default_factory=list)

    def format(self, digits: int = 3, *, with_ci: bool = True) -> str:
        s = f"{self.value:.{digits}f}"
        if with_ci and self.lo is not None and self.hi is not None:
            half = (self.hi - self.lo) / 2.0
            s += f" \\pm {half:.{digits}f}"
        return s


def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return math.nan
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def bootstrap_ci(values: Iterable[float], *, n_boot: int = 10000, alpha: float = 0.05, seed: int = 0) -> Estimate:
    """Percentile bootstrap CI of the mean.

    A deterministic seed keeps the paper reproducible; ``random.Random`` is used
    rather than numpy so this module has no hard dependency.
    """
    import random

    vals = [float(v) for v in values]
    if not vals:
        return Estimate(value=math.nan)
    mean = sum(vals) / len(vals)
    if len(vals) == 1:
        return Estimate(value=mean, n=1)
    rng = random.Random(seed)
    means = []
    n = len(vals)
    for _ in range(n_boot):
        means.append(sum(vals[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    return Estimate(
        value=mean,
        lo=_percentile(means, alpha / 2),
        hi=_percentile(means, 1 - alpha / 2),
        n=n,
    )


def estimate(runs: list[RunRecord], metric: str, **kwargs) -> Estimate:
    """Pool a metric across runs, keeping the run ids that fed it."""
    values: list[float] = []
    sources: list[str] = []
    for r in runs:
        v = r.metrics.get(metric)
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            values.extend(float(x) for x in v)
        else:
            values.append(float(v))
        sources.append(r.run_id)
    est = bootstrap_ci(values, **kwargs)
    est.source_runs = sources
    return est


# --------------------------------------------------------------------------
# number registry -> LaTeX macros
# --------------------------------------------------------------------------

class NumberRegistry:
    """Collects every number the paper is allowed to print.

    Emits ``numbers.tex`` full of ``\\newcommand`` definitions.  The paper then
    writes ``\\nAccuracyOurs`` instead of ``0.873``, so a stale number is a
    compile error rather than a silent lie.
    """

    _NAME_RE = re.compile(r"^[A-Za-z]+$")

    def __init__(self) -> None:
        self.entries: dict[str, dict] = {}

    def add(self, name: str, value: str | float | Estimate, *, digits: int = 3,
            with_ci: bool = True, provenance: str = "") -> str:
        macro = "".join(part.capitalize() for part in re.split(r"[^A-Za-z0-9]+", name) if part)
        macro = re.sub(r"\d", lambda m: "ZOTTFSSENN"[int(m.group(0))], macro)
        if not self._NAME_RE.match(macro):
            raise ValueError(f"macro name {macro!r} derived from {name!r} is not a valid LaTeX command name")
        if isinstance(value, Estimate):
            rendered = value.format(digits, with_ci=with_ci)
            prov = provenance or f"runs={','.join(value.source_runs)} n={value.n}"
        elif isinstance(value, float):
            rendered = f"{value:.{digits}f}"
            prov = provenance
        else:
            rendered = str(value)
            prov = provenance
        if macro in self.entries and self.entries[macro]["value"] != rendered:
            raise ValueError(f"macro {macro} redefined with a different value "
                             f"({self.entries[macro]['value']!r} then {rendered!r})")
        self.entries[macro] = {"value": rendered, "provenance": prov, "source_name": name}
        return f"\\n{macro}"

    def write(self, path: str) -> None:
        lines = [
            "% Generated by paperengine.provenance -- do not edit by hand.",
            "% Every number printed in this paper is defined here and traced to a run record.",
            "",
        ]
        for macro in sorted(self.entries):
            e = self.entries[macro]
            # A value carrying \pm or other math-only markup has to survive
            # being dropped into running text, so wrap it rather than trusting
            # the call site. An escaped percent is *not* math-only, and wrapping
            # it was a real bug: math mode discards spaces, so an interval came
            # out as "78.2%[73.6, 82.4]" and a range as "1.5%to35%".
            value = e["value"]
            if re.search(r"\\(?:pm|times|cdot|leq|geq|approx|infty)|[_^]", value):
                value = f"\\ensuremath{{{value}}}"
            lines.append(f"% {e['source_name']}: {e['provenance']}")
            lines.append(f"\\newcommand{{\\n{macro}}}{{{value}}}")
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")

    def manifest(self) -> dict:
        return {f"\\n{k}": v for k, v in sorted(self.entries.items())}


# --------------------------------------------------------------------------
# audit: catch hand-typed numbers
# --------------------------------------------------------------------------

# Contexts where a bare numeral is legitimate and must not be flagged.
_SAFE_PATTERNS = [
    re.compile(r"\\(?:cite|citep|citet|ref|label|autoref|eqref|input|include|includegraphics|url|href|bibliography|documentclass|usepackage|newcommand|renewcommand|定)[^{]*\{[^}]*\}"),
    re.compile(r"%.*$", re.MULTILINE),
    re.compile(r"\\begin\{(?:equation|align|gather|figure|table)\*?\}\[[^\]]*\]"),
    re.compile(r"\d+(?:\.\d+)?\s*(?:pt|em|ex|cm|mm|in|\\textwidth|\\linewidth|\\columnwidth)"),
    re.compile(r"\[[^\]]*\d[^\]]*\]"),          # optional args: [0.5\textwidth], [h!]
    # Inline math, bounded. An unbounded $...$ pairs the first dollar with the
    # next one anywhere in the file, so a single stray or escaped dollar makes
    # the mask run away: on this paper it swallowed 43% of the source, including
    # a hand-typed results table, and the audit passed. Inline math is short and
    # never spans a blank line.
    re.compile(r"\$(?:[^$\n]{0,160})\$"),
    re.compile(r"\\begin\{(equation|align|gather|split|array|cases)\*?\}.*?\\end\{\1\*?\}", re.DOTALL),
    re.compile(r"\\(?:sec|fig|tab|eq|app|thm|lem|prop)[A-Za-z]*:\S*"),
    re.compile(r"(?:Section|Figure|Table|Appendix|Equation|Theorem|Lemma|Definition)~?\\?ref"),
    re.compile(r"\\n[A-Z][A-Za-z]*"),            # our own provenance macros
    # Digits inside a proper noun: MATH-500, CIFAR-10, GPT-4, ARC-Challenge.
    # These name a thing rather than measure one, and flagging them trains the
    # author to widen the whitelist, which is how an audit stops working.
    re.compile(r"\b[A-Za-z]{2,}[-‑]\d+[A-Za-z]*\b"),
]

_NUM_RE = re.compile(r"(?<![\w\\.])\d+(?:\.\d+)?(?:e-?\d+)?%?")
# Numbers that are structural rather than empirical.
_ALLOWED_LITERALS = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
                     "100", "1000", "0.5", "1.0", "2.0", "0.05", "0.01", "95"}


@dataclasses.dataclass
class AuditFinding:
    tex_file: str
    line: int
    literal: str
    context: str


def audit_tex(paths: Iterable[str], *, allowed: Optional[set[str]] = None) -> list[AuditFinding]:
    """Flag numeric literals that did not come from the registry.

    Deliberately noisy: it is far cheaper to whitelist a year than to publish a
    number nobody can reproduce.
    """
    allowed = (allowed or set()) | _ALLOWED_LITERALS
    findings: list[AuditFinding] = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        masked = text
        for pat in _SAFE_PATTERNS:
            masked = pat.sub(lambda m: " " * len(m.group(0)), masked)
        for m in _NUM_RE.finditer(masked):
            lit = m.group(0)
            if lit.rstrip("%") in allowed:
                continue
            if re.fullmatch(r"(19|20)\d{2}", lit):    # a year in prose
                continue
            line = text.count("\n", 0, m.start()) + 1
            start = max(0, m.start() - 55)
            findings.append(AuditFinding(
                tex_file=os.path.basename(path), line=line, literal=lit,
                context=re.sub(r"\s+", " ", text[start:m.end() + 45]).strip(),
            ))
    return findings


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Audit LaTeX sources for hand-typed numbers.")
    ap.add_argument("tex", nargs="+", help="LaTeX files to audit")
    ap.add_argument("--allow", default="", help="comma-separated literals that are legitimately hand-written")
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args(argv)

    allowed = {s.strip() for s in args.allow.split(",") if s.strip()}
    findings = audit_tex(args.tex, allowed=allowed)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump([dataclasses.asdict(f) for f in findings], fh, indent=2)

    if not findings:
        print("NUMBER AUDIT PASSED: every empirical number comes from a \\n macro.")
        return 0
    print(f"NUMBER AUDIT: {len(findings)} hand-typed numeric literal(s) found.\n")
    for f in findings:
        print(f"  {f.tex_file}:{f.line}  {f.literal}")
        print(f"      ...{f.context}...")
    print("\nEach must either be replaced by a registry macro or whitelisted with --allow.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
