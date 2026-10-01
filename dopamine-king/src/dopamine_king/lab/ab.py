"""A/B testing toolkit: frequentist test, Bayesian comparison, sample sizes and peeking simulation."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from statistics import NormalDist

_N = NormalDist()


def wilson_interval(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 1.0
    z = _N.inv_cdf(1 - (1 - level) / 2)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


@dataclass
class ABResult:
    n_a: int
    n_b: int
    rate_a: float
    rate_b: float
    diff: float                       # b minus a, absolute
    rel_uplift: float | None          # (b - a) / a
    z: float
    p_value: float                    # two sided
    ci_diff: tuple[float, float]      # Newcombe hybrid score interval for b minus a
    wilson_a: tuple[float, float]
    wilson_b: tuple[float, float]
    alpha: float
    significant: bool

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        for key in ("rate_a", "rate_b", "diff", "z", "p_value"):
            d[key] = round(d[key], 6)
        d["rel_uplift"] = None if self.rel_uplift is None else round(self.rel_uplift, 4)
        d["ci_diff"] = [round(v, 6) for v in self.ci_diff]
        d["wilson_a"] = [round(v, 6) for v in self.wilson_a]
        d["wilson_b"] = [round(v, 6) for v in self.wilson_b]
        return d


def two_proportion_test(conv_a: int, n_a: int, conv_b: int, n_b: int, alpha: float = 0.05) -> ABResult:
    """Pooled two-proportion z test with a Newcombe interval for the difference."""
    pa, pb = conv_a / n_a, conv_b / n_b
    pooled = (conv_a + conv_b) / (n_a + n_b)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n_a + 1 / n_b))
    z = (pb - pa) / se if se else 0.0
    p_value = 2 * (1 - _N.cdf(abs(z)))
    la, ua = wilson_interval(conv_a, n_a, 1 - alpha)
    lb, ub = wilson_interval(conv_b, n_b, 1 - alpha)
    lo = (pb - pa) - math.sqrt((pb - lb) ** 2 + (ua - pa) ** 2)
    hi = (pb - pa) + math.sqrt((ub - pb) ** 2 + (pa - la) ** 2)
    return ABResult(
        n_a, n_b, pa, pb, pb - pa, (pb - pa) / pa if pa else None, z, p_value, (lo, hi),
        (la, ua), (lb, ub), alpha, p_value < alpha,
    )


def sample_size_per_arm(baseline: float, mde_rel: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Visitors needed per arm to detect a relative lift of ``mde_rel`` over ``baseline`` (two sided)."""
    p1 = baseline
    p2 = baseline * (1 + mde_rel)
    if not (0 < p1 < 1 and 0 < p2 < 1):
        raise ValueError("baseline and lifted rate must be inside (0, 1)")
    pbar = (p1 + p2) / 2
    za, zb = _N.inv_cdf(1 - alpha / 2), _N.inv_cdf(power)
    num = (za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return math.ceil(num / (p2 - p1) ** 2)


def holm_bonferroni(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    """Step-down correction for several variants against one control. Returns reject flags."""
    order = sorted(range(len(p_values)), key=lambda i: p_values[i])
    reject = [False] * len(p_values)
    m = len(p_values)
    for rank, i in enumerate(order):
        if p_values[i] <= alpha / (m - rank):
            reject[i] = True
        else:
            break
    return reject


@dataclass
class BayesResult:
    p_b_better: float
    expected_uplift: float            # mean of (b - a) / a over posterior draws
    expected_loss_choose_a: float     # expected conversion rate lost if we ship A but B is better
    expected_loss_choose_b: float
    credible_a: tuple[float, float]
    credible_b: tuple[float, float]
    draws: int

    def to_dict(self) -> dict:
        return {
            "p_b_better": round(self.p_b_better, 4), "expected_uplift": round(self.expected_uplift, 4),
            "expected_loss_choose_a": round(self.expected_loss_choose_a, 6),
            "expected_loss_choose_b": round(self.expected_loss_choose_b, 6),
            "credible_a": [round(v, 5) for v in self.credible_a],
            "credible_b": [round(v, 5) for v in self.credible_b], "draws": self.draws,
        }


def bayes_ab(
    conv_a: int, n_a: int, conv_b: int, n_b: int, *,
    prior: tuple[float, float] = (1.0, 1.0), draws: int = 20000, seed: int = 0,
) -> BayesResult:
    """Beta-Binomial comparison by seeded Monte Carlo."""
    rng = random.Random(seed)
    a1, b1 = prior[0] + conv_a, prior[1] + n_a - conv_a
    a2, b2 = prior[0] + conv_b, prior[1] + n_b - conv_b
    sa = [rng.betavariate(a1, b1) for _ in range(draws)]
    sb = [rng.betavariate(a2, b2) for _ in range(draws)]
    wins = sum(1 for x, y in zip(sa, sb) if y > x)
    uplift = sum((y - x) / x for x, y in zip(sa, sb) if x > 0) / draws
    loss_a = sum(max(y - x, 0.0) for x, y in zip(sa, sb)) / draws
    loss_b = sum(max(x - y, 0.0) for x, y in zip(sa, sb)) / draws
    sa_sorted, sb_sorted = sorted(sa), sorted(sb)
    lo, hi = int(0.025 * draws), int(0.975 * draws) - 1
    return BayesResult(wins / draws, uplift, loss_a, loss_b,
                       (sa_sorted[lo], sa_sorted[hi]), (sb_sorted[lo], sb_sorted[hi]), draws)


def peeking_false_positive_rate(
    looks: int, n_per_look: int = 200, base_rate: float = 0.05, alpha: float = 0.05,
    trials: int = 1000, seed: int = 0,
) -> float:
    """Share of A/A tests (no real difference) declared significant when checked at every look.

    Demonstrates why stopping at the first p < alpha inflates false positives far above alpha.
    """
    rng = random.Random(seed)
    false_pos = 0
    for _ in range(trials):
        ca = cb = na = nb = 0
        hit = False
        for _ in range(looks):
            ca += sum(1 for _ in range(n_per_look) if rng.random() < base_rate)
            cb += sum(1 for _ in range(n_per_look) if rng.random() < base_rate)
            na += n_per_look
            nb += n_per_look
            if ca + cb == 0:
                continue
            if two_proportion_test(ca, na, cb, nb, alpha).significant:
                hit = True
                break
        false_pos += hit
    return false_pos / trials
