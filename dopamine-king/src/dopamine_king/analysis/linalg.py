"""Tiny dense linear algebra and regression helpers in pure Python.

Column-major dot products via ``sum(map(mul, ...))`` keep the heavy loops in C, which is fast
enough for the few thousand rows and a few dozen features this project works with.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from operator import mul
from typing import Sequence


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def std(xs: Sequence[float], ddof: int = 0) -> float:
    n = len(xs)
    if n - ddof <= 0:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - ddof))


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    sx, sy = std(xs), std(ys)
    if not sx or not sy:
        return 0.0
    mx, my = mean(xs), mean(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (len(xs) * sx * sy)


def _ranks(xs: Sequence[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    return pearson(_ranks(xs), _ranks(ys))


def quantile(sorted_vals: Sequence[float], q: float) -> float:
    """Linear interpolation quantile of an already sorted sequence."""
    if not sorted_vals:
        return 0.0
    pos = q * (len(sorted_vals) - 1)
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def percentile_rank(sorted_vals: Sequence[float], x: float) -> float:
    """Mid-rank percentile (0..100) of x within a sorted sequence."""
    n = len(sorted_vals)
    if n == 0:
        return 50.0
    from bisect import bisect_left, bisect_right
    below, upto = bisect_left(sorted_vals, x), bisect_right(sorted_vals, x)
    return 100.0 * (below + 0.5 * (upto - below)) / n


def solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gauss-Jordan elimination with partial pivoting."""
    n = len(a)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            raise ValueError("singular matrix")
        m[col], m[piv] = m[piv], m[col]
        pv = m[col][col]
        for j in range(col, n + 1):
            m[col][j] /= pv
        for r in range(n):
            if r != col and m[r][col]:
                f = m[r][col]
                for j in range(col, n + 1):
                    m[r][j] -= f * m[col][j]
    return [m[i][n] for i in range(n)]


@dataclass
class RidgeFit:
    intercept: float
    coef: list[float]          # original feature units
    coef_std: list[float]      # effect of +1 SD of the feature, in units of y
    means: list[float]
    stds: list[float]
    r2: float
    n: int

    def predict_one(self, row: Sequence[float]) -> float:
        return self.intercept + sum(c * v for c, v in zip(self.coef, row))

    def predict(self, rows: Sequence[Sequence[float]]) -> list[float]:
        return [self.predict_one(r) for r in rows]


def _columns(rows: Sequence[Sequence[float]]) -> list[list[float]]:
    return [list(c) for c in zip(*rows)] if rows else []


def ridge_fit(rows: Sequence[Sequence[float]], y: Sequence[float], lam: float = 1.0) -> RidgeFit:
    """Ridge regression on standardised columns with an unpenalised intercept."""
    n = len(rows)
    cols = _columns(rows)
    p = len(cols)
    means = [mean(c) for c in cols]
    stds = [std(c) or 1.0 for c in cols]
    z = [[(v - means[j]) / stds[j] for v in cols[j]] for j in range(p)]
    ybar = mean(y)
    yc = [v - ybar for v in y]
    gram = [[sum(map(mul, z[i], z[j])) + (lam if i == j else 0.0) for j in range(p)] for i in range(p)]
    rhs = [sum(map(mul, z[i], yc)) for i in range(p)]
    w = solve(gram, rhs) if p else []
    coef = [w[j] / stds[j] for j in range(p)]
    intercept = ybar - sum(coef[j] * means[j] for j in range(p))
    preds = [intercept + sum(coef[j] * rows[i][j] for j in range(p)) for i in range(n)]
    sst = sum(v * v for v in yc)
    sse = sum((y[i] - preds[i]) ** 2 for i in range(n))
    return RidgeFit(intercept, coef, w, means, stds, 1.0 - sse / sst if sst else 0.0, n)


def kfold_r2(rows: Sequence[Sequence[float]], y: Sequence[float], lam: float = 1.0, k: int = 5, seed: int = 0) -> float:
    """Out-of-fold R squared."""
    n = len(rows)
    idx = list(range(n))
    random.Random(seed).shuffle(idx)
    folds = [idx[i::k] for i in range(k)]
    preds = [0.0] * n
    for fold in folds:
        held = set(fold)
        train = [i for i in idx if i not in held]
        fit = ridge_fit([rows[i] for i in train], [y[i] for i in train], lam)
        for i in fold:
            preds[i] = fit.predict_one(rows[i])
    ybar = mean(y)
    sst = sum((v - ybar) ** 2 for v in y)
    sse = sum((y[i] - preds[i]) ** 2 for i in range(n))
    return 1.0 - sse / sst if sst else 0.0


def bootstrap_coef_ci(
    rows: Sequence[Sequence[float]], y: Sequence[float], lam: float = 1.0,
    n_boot: int = 200, seed: int = 0, level: float = 0.95,
) -> list[tuple[float, float]]:
    """Percentile bootstrap intervals for the standardised ridge coefficients."""
    rng = random.Random(seed)
    n = len(rows)
    p = len(rows[0]) if rows else 0
    draws: list[list[float]] = [[] for _ in range(p)]
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        try:
            fit = ridge_fit([rows[i] for i in idx], [y[i] for i in idx], lam)
        except ValueError:
            continue
        for j in range(p):
            draws[j].append(fit.coef_std[j])
    lo_q, hi_q = (1 - level) / 2, 1 - (1 - level) / 2
    return [(quantile(sorted(d), lo_q), quantile(sorted(d), hi_q)) if d else (0.0, 0.0) for d in draws]


def nnls(rows: Sequence[Sequence[float]], y: Sequence[float], iters: int = 400) -> list[float]:
    """Non-negative least squares by cyclic coordinate descent on centred data (no intercept)."""
    cols = _columns(rows)
    p = len(cols)
    means = [mean(c) for c in cols]
    xc = [[v - means[j] for v in cols[j]] for j in range(p)]
    ybar = mean(y)
    r = [v - ybar for v in y]
    w = [0.0] * p
    norms = [sum(v * v for v in c) or 1.0 for c in xc]
    for _ in range(iters):
        moved = 0.0
        for j in range(p):
            grad = sum(map(mul, xc[j], r))
            new = max(0.0, w[j] + grad / norms[j])
            delta = new - w[j]
            if delta:
                r = [ri - delta * xv for ri, xv in zip(r, xc[j])]
                w[j] = new
                moved = max(moved, abs(delta))
        if moved < 1e-9:
            break
    return w
