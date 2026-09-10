"""What each benchmark can and cannot resolve.

The audit finds that half the gaps reported on named benchmarks are smaller than
those benchmarks can distinguish. That is a finding about the literature. This
turns it into something an author can use before writing the sentence: for each
benchmark in common use, the smallest accuracy difference it can support at
conventional power, given only its published evaluation split.

The number depends on where on the scale the systems sit, because a binomial
variance is largest at one half, so it is tabulated at several accuracies. It is
computed under independence, which is the conservative reading: two systems
scored on the same items are correlated, and a paired analysis resolves finer.
The paired figure at a plausible correlation is given alongside.

Nothing here is specific to our corpus. It is a property of the benchmarks.
"""

from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

from benchmark_resolution import BENCHMARKS, resolvable_gap  # noqa: E402

ACCURACIES = (0.50, 0.70, 0.90)
PAIRED_RHO = 0.5


def table(alpha: float = 0.05, power: float = 0.8) -> list:
    rows = []
    for name, (_, size) in sorted(BENCHMARKS.items(), key=lambda kv: kv[1][1]):
        row = {"benchmark": name, "split_size": size}
        for p in ACCURACIES:
            row[f"mde_at_{int(p * 100)}"] = round(
                resolvable_gap(size, p, alpha=alpha, power=power), 2)
        row["mde_at_70_paired"] = round(
            resolvable_gap(size, 0.70, alpha=alpha, power=power) * math.sqrt(1 - PAIRED_RHO), 2)
        rows.append(row)
    return rows


def main() -> int:
    rows = table()
    out = {
        "alpha": 0.05, "power": 0.8, "paired_rho": PAIRED_RHO,
        "note": ("Smallest difference in accuracy, in percentage points, that a "
                 "benchmark of this size can distinguish from zero at the stated "
                 "power. Independent-binomial reading; the paired column assumes "
                 "the two systems are scored on the same items with correlation "
                 f"{PAIRED_RHO}."),
        "rows": rows,
    }
    os.makedirs("out", exist_ok=True)
    with open("out/benchmark_mde_table.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)

    print(f"{'benchmark':<20}{'items':>8}{'@50%':>8}{'@70%':>8}{'@90%':>8}{'@70% paired':>13}")
    for r in rows:
        print(f"{r['benchmark']:<20}{r['split_size']:>8}{r['mde_at_50']:>8}"
              f"{r['mde_at_70']:>8}{r['mde_at_90']:>8}{r['mde_at_70_paired']:>13}")
    print("\n-> out/benchmark_mde_table.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
