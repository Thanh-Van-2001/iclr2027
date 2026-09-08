"""Statistical machinery for defensible empirical claims.

Reviewers reject empirical papers for a small number of recurring reasons, and
most of them are statistical: one seed, no interval, a leaderboard gap inside
the noise, or twenty configurations searched and the best one reported as if it
were the only one tried.  The last of these is the interesting case, because
quantitative finance has spent thirty years building corrections for exactly it
and machine learning has largely not imported them.

Everything here is dependency-free beyond the standard library, so it runs
anywhere the paper builds.
"""

from __future__ import annotations

import math
import random
from typing import Callable, Iterable, Optional, Sequence


# --------------------------------------------------------------------------
# normal distribution helpers
# --------------------------------------------------------------------------

def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p: float) -> float:
    """Inverse normal CDF (Acklam's rational approximation, |err| < 1.15e-9)."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must lie strictly between 0 and 1")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


EULER_MASCHERONI = 0.5772156649015329


# --------------------------------------------------------------------------
# comparing two systems
# --------------------------------------------------------------------------

def paired_permutation_test(
    a: Sequence[float],
    b: Sequence[float],
    *,
    n_perm: int = 20000,
    seed: int = 0,
    statistic: Callable[[Sequence[float]], float] = lambda d: sum(d) / len(d),
) -> dict:
    """Exact-in-the-limit paired test with no distributional assumption.

    The right default for benchmark comparisons: the per-item scores of two
    systems are paired, and the null is that the labels on each pair could be
    swapped without changing anything.
    """
    if len(a) != len(b):
        raise ValueError("paired test needs equal-length samples")
    diffs = [float(x) - float(y) for x, y in zip(a, b)]
    observed = statistic(diffs)
    rng = random.Random(seed)
    extreme = 0
    for _ in range(n_perm):
        flipped = [d if rng.random() < 0.5 else -d for d in diffs]
        if abs(statistic(flipped)) >= abs(observed):
            extreme += 1
    # Add-one correction: a permutation p-value is never exactly zero.
    p = (extreme + 1) / (n_perm + 1)
    return {"observed_diff": observed, "p_value": p, "n_pairs": len(diffs), "n_perm": n_perm}


def bootstrap_diff_ci(
    a: Sequence[float],
    b: Sequence[float],
    *,
    n_boot: int = 10000,
    alpha: float = 0.05,
    seed: int = 0,
    paired: bool = True,
) -> dict:
    """Confidence interval on the difference in means."""
    rng = random.Random(seed)
    if paired:
        if len(a) != len(b):
            raise ValueError("paired bootstrap needs equal-length samples")
        diffs = [float(x) - float(y) for x, y in zip(a, b)]
        n = len(diffs)
        boots = [sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot)]
        point = sum(diffs) / n
    else:
        na, nb = len(a), len(b)
        boots = [
            sum(a[rng.randrange(na)] for _ in range(na)) / na
            - sum(b[rng.randrange(nb)] for _ in range(nb)) / nb
            for _ in range(n_boot)
        ]
        point = sum(a) / na - sum(b) / nb
    boots.sort()
    lo = boots[max(0, int(alpha / 2 * n_boot) - 1)]
    hi = boots[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return {"diff": point, "lo": lo, "hi": hi, "alpha": alpha,
            "excludes_zero": (lo > 0) or (hi < 0)}


def minimum_detectable_effect(n: int, sd: float, *, alpha: float = 0.05, power: float = 0.8) -> float:
    """Smallest difference a benchmark of ``n`` items could detect.

    Useful for the argument that an entire leaderboard is under-powered: if the
    reported gaps are below this value, the ranking is noise.
    """
    if n <= 1:
        return math.inf
    z_a = norm_ppf(1 - alpha / 2)
    z_b = norm_ppf(power)
    return (z_a + z_b) * sd / math.sqrt(n)


def wilson_interval(successes: int, n: int, *, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson score interval for an accuracy on ``n`` benchmark items."""
    if n == 0:
        return (0.0, 1.0)
    z = norm_ppf(1 - alpha / 2)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


# --------------------------------------------------------------------------
# many comparisons at once
# --------------------------------------------------------------------------

def holm_bonferroni(p_values: Sequence[float], alpha: float = 0.05) -> list[bool]:
    """Family-wise error control.  Returns one rejection flag per hypothesis."""
    order = sorted(range(len(p_values)), key=lambda i: p_values[i])
    m = len(p_values)
    reject = [False] * m
    for rank, idx in enumerate(order):
        if p_values[idx] <= alpha / (m - rank):
            reject[idx] = True
        else:
            break
    return reject


def benjamini_hochberg(p_values: Sequence[float], alpha: float = 0.05) -> list[bool]:
    """False-discovery-rate control, the right default when m is large."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    reject = [False] * m
    k_max = -1
    for rank, idx in enumerate(order, start=1):
        if p_values[idx] <= alpha * rank / m:
            k_max = rank
    for rank, idx in enumerate(order, start=1):
        if rank <= k_max:
            reject[idx] = True
    return reject


# --------------------------------------------------------------------------
# selection bias: the correction machine learning mostly has not imported
# --------------------------------------------------------------------------

def expected_max_of_normals(n_trials: int) -> float:
    """Expected maximum of ``n`` independent standard normals.

    The quantity that makes selection bias concrete: search a thousand
    configurations that are all worthless and the best one still scores about
    3.2 standard deviations above zero.
    """
    if n_trials <= 1:
        return 0.0
    e = EULER_MASCHERONI
    return ((1 - e) * norm_ppf(1 - 1.0 / n_trials)
            + e * norm_ppf(1 - 1.0 / (n_trials * math.e)))


def deflated_score(
    observed: float,
    *,
    n_trials: int,
    variance_across_trials: float,
    n_observations: int,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> dict:
    """Probability that a selected result beats zero once the search is charged for.

    This is the deflated Sharpe ratio of Bailey and Lopez de Prado, stated in
    neutral terms so it applies to any selected performance statistic: an
    accuracy chosen out of a hyperparameter sweep, a prompt chosen out of a
    prompt search, or an architecture chosen out of a NAS run.

    ``observed`` is the winning statistic, ``variance_across_trials`` the
    variance of that statistic across everything that was tried, and
    ``n_observations`` the number of evaluation points behind the winner.

    Returns the deflated probability; below roughly 0.95 the result is not
    distinguishable from the best of a lucky search.
    """
    if n_trials < 1 or n_observations < 2:
        raise ValueError("need at least one trial and two observations")
    threshold = math.sqrt(max(variance_across_trials, 0.0)) * expected_max_of_normals(n_trials)
    denom = math.sqrt(max(1e-12, 1 - skew * observed + (kurtosis - 1) / 4.0 * observed ** 2))
    z = (observed - threshold) * math.sqrt(n_observations - 1) / denom
    return {
        "observed": observed,
        "selection_threshold": threshold,
        "n_trials": n_trials,
        "deflated_probability": norm_cdf(z),
        "survives": norm_cdf(z) >= 0.95,
    }


def probability_of_selection_overfit(
    trial_scores_by_split: Sequence[Sequence[float]],
) -> dict:
    """Probability that the in-sample winner underperforms the median out of sample.

    A rank-based diagnostic in the spirit of the combinatorially symmetric
    cross-validation of Bailey et al.  ``trial_scores_by_split`` is indexed
    ``[split][trial]``: for each split, the score every candidate achieved.
    Splits are used pairwise, one as selection set and the other as holdout.
    """
    splits = [list(map(float, s)) for s in trial_scores_by_split]
    if len(splits) < 2:
        raise ValueError("need at least two splits")
    n_trials = len(splits[0])
    if any(len(s) != n_trials for s in splits):
        raise ValueError("every split must score the same set of trials")

    logits, overfit = [], 0
    pairs = 0
    for i in range(len(splits)):
        for j in range(len(splits)):
            if i == j:
                continue
            sel, hold = splits[i], splits[j]
            best = max(range(n_trials), key=lambda t: sel[t])
            ranked = sorted(range(n_trials), key=lambda t: hold[t])
            rank = ranked.index(best) + 1
            omega = rank / (n_trials + 1)
            omega = min(max(omega, 1e-6), 1 - 1e-6)
            logits.append(math.log(omega / (1 - omega)))
            if omega <= 0.5:
                overfit += 1
            pairs += 1
    return {
        "pbo": overfit / pairs,
        "n_pairs": pairs,
        "n_trials": n_trials,
        "mean_logit": sum(logits) / len(logits),
    }


# --------------------------------------------------------------------------
# forecast comparison
# --------------------------------------------------------------------------

def diebold_mariano(
    loss_a: Sequence[float],
    loss_b: Sequence[float],
    *,
    horizon: int = 1,
) -> dict:
    """Test of equal predictive accuracy between two forecasters.

    Uses a Newey-West long-run variance so that autocorrelated losses -- the
    normal case for anything with a time index -- do not inflate significance.
    """
    if len(loss_a) != len(loss_b):
        raise ValueError("loss series must be the same length")
    d = [float(x) - float(y) for x, y in zip(loss_a, loss_b)]
    n = len(d)
    if n < 8:
        raise ValueError("too few observations for a meaningful test")
    dbar = sum(d) / n

    def autocov(k: int) -> float:
        return sum((d[t] - dbar) * (d[t - k] - dbar) for t in range(k, n)) / n

    lag = max(0, horizon - 1)
    lrv = autocov(0) + 2.0 * sum((1 - k / (lag + 1)) * autocov(k) for k in range(1, lag + 1))
    if lrv <= 0:
        return {"statistic": math.nan, "p_value": math.nan,
                "note": "non-positive long-run variance; series may be degenerate"}
    stat = dbar / math.sqrt(lrv / n)
    # Harvey-Leybourne-Newbold small-sample correction.
    corr = math.sqrt((n + 1 - 2 * horizon + horizon * (horizon - 1) / n) / n)
    stat *= corr
    return {"statistic": stat, "p_value": 2 * (1 - norm_cdf(abs(stat))),
            "mean_loss_diff": dbar, "n": n}


# --------------------------------------------------------------------------
# agreement
# --------------------------------------------------------------------------

def cohens_kappa(a: Sequence, b: Sequence) -> float:
    """Chance-corrected agreement, for LLM-judge versus human comparisons."""
    if len(a) != len(b) or not a:
        raise ValueError("rating vectors must be equal-length and non-empty")
    labels = sorted(set(a) | set(b))
    n = len(a)
    observed = sum(1 for x, y in zip(a, b) if x == y) / n
    expected = sum((sum(1 for x in a if x == l) / n) * (sum(1 for y in b if y == l) / n) for l in labels)
    if expected >= 1.0:
        return 1.0
    return (observed - expected) / (1 - expected)


def krippendorff_alpha_nominal(ratings: Sequence[Sequence[Optional[str]]]) -> float:
    """Nominal-scale reliability across any number of raters, missing data allowed.

    ``ratings`` is indexed ``[rater][item]``; use ``None`` for a missing rating.
    """
    n_items = len(ratings[0]) if ratings else 0
    units = []
    for i in range(n_items):
        vals = [r[i] for r in ratings if i < len(r) and r[i] is not None]
        if len(vals) >= 2:
            units.append(vals)
    if not units:
        return float("nan")
    total = sum(len(u) for u in units)
    observed = 0.0
    for u in units:
        m = len(u)
        same = sum(1 for i in range(m) for j in range(m) if i != j and u[i] == u[j])
        observed += same / (m - 1)
    observed /= total
    allvals = [v for u in units for v in u]
    expected = sum((allvals.count(v) / total) * ((allvals.count(v) - 1) / (total - 1))
                   for v in set(allvals))
    if expected >= 1.0:
        return 1.0
    return (observed - expected) / (1 - expected)
