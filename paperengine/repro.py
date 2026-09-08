"""Reproducibility: the thing reviewers complain about most.

Across 1,542 annotated ICLR reviews, replicability is raised as a criticism in
94% of the reviews that mention it at all -- the most lopsided ratio of any
aspect measured.  It is also the cheapest to fix, because unlike novelty it is
entirely under the authors' control.

Three jobs live here:

``capture_environment``
    Record exactly what produced a result: interpreter, platform, installed
    versions, git revision.  A result whose environment was never recorded
    cannot be reproduced later even by its own author.

``seed_everything`` / :class:`ExperimentRunner`
    Make every run repeatable and make multi-seed the default rather than an
    afterthought.  A single-seed number is the specific thing the methodologist
    reviewer rejects.

``package_artifact``
    Build the supplementary zip, and refuse to build it if it would break
    anonymity.  ICLR desk-rejects submissions whose supplementary material
    reveals author identity, and a stray ``.git`` directory does exactly that.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import zipfile
from typing import Callable, Iterable, Optional, Sequence

from . import provenance


# --------------------------------------------------------------------------
# environment
# --------------------------------------------------------------------------

def capture_environment(*, extra_packages: Sequence[str] = ()) -> dict:
    """Everything needed to explain why a number came out the way it did."""
    packages: dict[str, str] = {}
    interesting = set(extra_packages) | {
        "numpy", "pandas", "scipy", "matplotlib", "scikit-learn", "torch",
        "transformers", "datasets", "statsmodels", "pyarrow",
    }
    try:
        from importlib import metadata
        for dist in metadata.distributions():
            name = (dist.metadata["Name"] or "").lower()
            if name in interesting:
                packages[name] = dist.version
    except Exception:
        pass

    def _git(*args: str) -> str:
        try:
            return subprocess.run(["git", *args], capture_output=True, text=True,
                                  timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return "unknown"

    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "packages": dict(sorted(packages.items())),
        "git_revision": _git("rev-parse", "HEAD") or "unknown",
        "git_dirty": bool(_git("status", "--porcelain")),
    }


def seed_everything(seed: int) -> dict:
    """Seed every generator that might be in play, and report what was seeded.

    ``PYTHONHASHSEED`` cannot be changed after interpreter start, so it is
    reported rather than set; if it is not fixed, say so in the paper instead of
    pretending the run is bit-reproducible.
    """
    import random
    random.seed(seed)
    seeded = ["random"]

    try:
        import numpy as np
        np.random.seed(seed)
        seeded.append("numpy")
    except ImportError:
        pass
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
            seeded.append("torch.cuda")
        seeded.append("torch")
    except ImportError:
        pass

    return {
        "seed": seed,
        "seeded": seeded,
        "pythonhashseed": os.environ.get("PYTHONHASHSEED", "not set -- string hashing is not reproducible"),
    }


# --------------------------------------------------------------------------
# running experiments
# --------------------------------------------------------------------------

class ExperimentRunner:
    """A registry of experiments that all run the same way.

    Registering an experiment rather than calling it directly buys three things
    a reviewer asks for: every result carries its environment, every result is
    computed over several seeds, and ``reproduce.py --all`` regenerates the
    whole paper from nothing.
    """

    def __init__(self, *, timestamp: str, results_dir: str = provenance.RESULTS_DIR,
                 seeds: Sequence[int] = (0, 1, 2, 3, 4)) -> None:
        self.timestamp = timestamp
        self.results_dir = results_dir
        self.seeds = list(seeds)
        self._experiments: dict[str, tuple[Callable, dict]] = {}

    def register(self, name: str, *, config: Optional[dict] = None,
                 seeds: Optional[Sequence[int]] = None) -> Callable:
        """Decorator.  The wrapped function takes ``seed`` and returns metrics."""
        def deco(fn: Callable) -> Callable:
            cfg = dict(config or {})
            if seeds is not None:
                cfg["seeds"] = list(seeds)
            self._experiments[name] = (fn, cfg)
            return fn
        return deco

    def names(self) -> list[str]:
        return sorted(self._experiments)

    def run(self, name: str, *, verbose: bool = True) -> provenance.RunRecord:
        if name not in self._experiments:
            raise KeyError(f"no experiment named {name!r}; known: {self.names()}")
        fn, cfg = self._experiments[name]
        seeds = cfg.get("seeds", self.seeds)

        per_seed: dict[str, list] = {}
        for seed in seeds:
            seed_info = seed_everything(seed)
            out = fn(seed)
            if not isinstance(out, dict):
                raise TypeError(f"experiment {name!r} must return a dict of metrics, got {type(out)}")
            for k, v in out.items():
                per_seed.setdefault(k, []).append(v)
            if verbose:
                print(f"  {name} seed={seed}: " + ", ".join(f"{k}={v}" for k, v in out.items()))
            del seed_info

        rec = provenance.record_run(
            experiment=name,
            config={**cfg, "seeds": list(seeds), "environment": capture_environment()},
            metrics=per_seed,
            timestamp=self.timestamp,
            n_samples=len(seeds),
            results_dir=self.results_dir,
        )
        if verbose:
            print(f"  -> recorded {rec.run_id} ({rec.content_hash()})")
        return rec

    def run_all(self, *, verbose: bool = True) -> list[provenance.RunRecord]:
        return [self.run(n, verbose=verbose) for n in self.names()]


# --------------------------------------------------------------------------
# artifact packaging
# --------------------------------------------------------------------------

DEFAULT_EXCLUDES = [
    ".git/*", ".git", "*/.git/*", "__pycache__/*", "*/__pycache__/*", "*.pyc",
    "cache/*", "*/cache/*", ".env", "*.env", ".env_*", "*.pem", "*.key",
    "*.aux", "*.log", "*.fls", "*.fdb_latexmk", "*.blg", "*.synctex.gz",
    ".DS_Store", "*.ipynb_checkpoints/*", "node_modules/*",
]

# Anything matching these in a packaged file breaks double-blind review.
IDENTITY_PATTERNS = [
    (re.compile(r"https?://(?:www\.)?github\.com/([\w.-]+)/", re.I), "GitHub URL naming its owner"),
    (re.compile(r"https?://(?:www\.)?(?:gitlab|bitbucket)\.(?:com|org)/([\w.-]+)", re.I), "repository URL naming its owner"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}"), "email address"),
    (re.compile(r"(?i)\b(?:university|institute|laborator(?:y|ies)|academy)\s+of\s+[A-Z][\w]+"), "affiliation"),
    (re.compile(r"(?i)\bcopyright\s+(?:\(c\)\s*)?\d{4}\s+\w+"), "copyright line naming a holder"),
    (re.compile(r"/(?:home|Users)/([A-Za-z][\w.-]{2,})/"), "absolute path containing a username"),
    (re.compile(r"[A-Za-z]:[\\/]Users[\\/]([A-Za-z][\w.-]{2,})"), "Windows path containing a username"),
]

TEXTUAL = {".py", ".tex", ".bib", ".md", ".txt", ".json", ".yaml", ".yml",
           ".cfg", ".ini", ".toml", ".sh", ".csv", ".r", ".ipynb", ".html"}

# Placeholders that exist precisely to be non-identifying.  Flagging them
# trains the author to ignore the scanner, which is worse than not scanning.
BUILTIN_ALLOW = [
    r"@example\.(?:org|com|net)$",
    r"^anonymous@",
    r"^(?:noreply|no-reply)@",
    r"github\.com/(?:anonymous|anon)[\w.-]*/",
]


def _excluded(rel: str, patterns: Sequence[str]) -> bool:
    rel = rel.replace(os.sep, "/")
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(os.path.basename(rel), p)
               for p in patterns)


def scan_for_identity(root: str, *, excludes: Sequence[str] = DEFAULT_EXCLUDES,
                      allow: Sequence[str] = ()) -> list[dict]:
    """Find every string in the tree that could deanonymise the authors."""
    findings: list[dict] = []
    allow_res = [re.compile(a, re.I) for a in list(BUILTIN_ALLOW) + list(allow)]
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if not _excluded(os.path.relpath(os.path.join(dirpath, d), root), excludes)]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            if _excluded(rel, excludes):
                continue
            if os.path.splitext(fn)[1].lower() not in TEXTUAL:
                continue
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read(400_000)
            except OSError:
                continue
            for pat, why in IDENTITY_PATTERNS:
                for m in pat.finditer(text):
                    hit = m.group(0)
                    if any(a.search(hit) for a in allow_res):
                        continue
                    findings.append({
                        "file": rel.replace(os.sep, "/"),
                        "line": text.count("\n", 0, m.start()) + 1,
                        "match": hit[:90],
                        "why": why,
                    })
    return findings


def package_artifact(root: str, out_zip: str, *, excludes: Sequence[str] = DEFAULT_EXCLUDES,
                     allow: Sequence[str] = (), force: bool = False) -> dict:
    """Build the anonymous supplementary archive, refusing if it would leak.

    ``force`` exists for the case where a match is a false positive that cannot
    be expressed as an ``allow`` pattern, and it should be used only after
    reading every finding.
    """
    findings = scan_for_identity(root, excludes=excludes, allow=allow)
    if findings and not force:
        return {"packaged": False, "findings": findings,
                "reason": "anonymity scan found identifying strings; fix them or pass allow patterns"}

    os.makedirs(os.path.dirname(os.path.abspath(out_zip)) or ".", exist_ok=True)
    manifest: list[dict] = []
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames
                           if not _excluded(os.path.relpath(os.path.join(dirpath, d), root), excludes)]
            for fn in sorted(filenames):
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                if _excluded(rel, excludes):
                    continue
                with open(full, "rb") as fh:
                    blob = fh.read()
                zf.writestr(rel, blob)
                manifest.append({"path": rel, "bytes": len(blob),
                                 "sha256": hashlib.sha256(blob).hexdigest()[:16]})
        zf.writestr("MANIFEST.json", json.dumps(
            {"n_files": len(manifest), "files": manifest,
             "environment": capture_environment()}, indent=2))
    return {"packaged": True, "zip": out_zip, "n_files": len(manifest),
            "bytes": os.path.getsize(out_zip), "findings": findings}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Reproducibility and anonymous artifact packaging.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("env", help="print the captured environment")
    e.set_defaults(fn=lambda a: (print(json.dumps(capture_environment(), indent=2)), 0)[1])

    s = sub.add_parser("scan", help="scan a tree for strings that break anonymity")
    s.add_argument("--root", default=".")
    s.add_argument("--allow", action="append", default=[])
    s.set_defaults(fn=_cmd_scan)

    p = sub.add_parser("package", help="build the anonymous supplementary zip")
    p.add_argument("--root", default=".")
    p.add_argument("--out", default="out/supplementary.zip")
    p.add_argument("--allow", action="append", default=[])
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=_cmd_package)

    args = ap.parse_args(argv)
    return args.fn(args)


def _cmd_scan(args: argparse.Namespace) -> int:
    findings = scan_for_identity(args.root, allow=args.allow)
    if not findings:
        print("ANONYMITY SCAN PASSED: nothing identifying found.")
        return 0
    print(f"ANONYMITY SCAN: {len(findings)} identifying string(s).\n")
    for f in findings[:60]:
        print(f"  {f['file']}:{f['line']}  {f['why']}\n      {f['match']}")
    if len(findings) > 60:
        print(f"  ... and {len(findings) - 60} more")
    return 1


def _cmd_package(args: argparse.Namespace) -> int:
    res = package_artifact(args.root, args.out, allow=args.allow, force=args.force)
    if not res["packaged"]:
        print(f"NOT PACKAGED: {res['reason']}\n")
        for f in res["findings"][:40]:
            print(f"  {f['file']}:{f['line']}  {f['why']}\n      {f['match']}")
        return 1
    print(f"packaged {res['n_files']} files into {res['zip']} ({res['bytes'] / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
