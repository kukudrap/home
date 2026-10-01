"""Calibration: learn driver weights and the win-probability scale from a labelled corpus."""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from ..scoring import WEIGHTED_DRIVERS, load_spec
from .benchmark import ItemAnalysis
from .linalg import mean, nnls, pearson, spearman


@dataclass
class Calibration:
    weights: dict[str, float]
    n: int
    cv_spearman_default: float
    cv_spearman_calibrated: float
    logit_scale: float                 # points of score difference per unit of log-odds
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "weights": {k: round(v, 4) for k, v in self.weights.items()}, "n": self.n,
            "cv_spearman_default": round(self.cv_spearman_default, 4),
            "cv_spearman_calibrated": round(self.cv_spearman_calibrated, 4),
            "logit_scale": round(self.logit_scale, 3), "notes": self.notes,
        }

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), "utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Calibration":
        d = json.loads(Path(path).read_text("utf-8"))
        return cls(d["weights"], d["n"], d["cv_spearman_default"], d["cv_spearman_calibrated"], d["logit_scale"], d.get("notes", []))


def _matrix(rows: Sequence[ItemAnalysis]) -> list[list[float]]:
    return [[a.score.parts[d] / 100.0 for d in WEIGHTED_DRIVERS] for a in rows]


def _default_raw(a: ItemAnalysis, weights: dict[str, float]) -> float:
    wsum = sum(weights.values()) or 1.0
    return sum(weights[d] * a.score.parts[d] / 100.0 for d in WEIGHTED_DRIVERS) / wsum


def fit_logit_scale(scores: Sequence[float], success: Sequence[float], pairs: int = 4000, seed: int = 0) -> float:
    """Scale k in P(A beats B) = 1 / (1 + exp(-(sA - sB) / k)), fitted on random pairs by grid search."""
    rng = random.Random(seed)
    n = len(scores)
    sample = []
    for _ in range(pairs):
        i, j = rng.randrange(n), rng.randrange(n)
        if i != j and success[i] != success[j]:
            sample.append((scores[i] - scores[j], 1.0 if success[i] > success[j] else 0.0))
    if not sample:
        return 12.0
    best_k, best_ll = 12.0, -1e18
    for k in [x / 2 for x in range(4, 241)]:
        ll = 0.0
        for d, win in sample:
            p = min(1 - 1e-9, max(1e-9, 1.0 / (1.0 + math.exp(-d / k))))
            ll += math.log(p if win else 1 - p)
        if ll > best_ll:
            best_k, best_ll = k, ll
    return best_k


def calibrate_weights(analyses: Sequence[ItemAnalysis], *, k: int = 5, seed: int = 0, min_n: int = 80) -> Calibration:
    spec_weights = dict(load_spec()["params"]["weights"])
    rows = [a for a in analyses if a.success is not None]
    if len(rows) < min_n:
        return Calibration(spec_weights, len(rows), 0.0, 0.0, 12.0,
                           [f"Not enough labelled items ({len(rows)} < {min_n}); default weights kept."])
    y = [float(a.success) for a in rows]  # type: ignore[arg-type]
    x = _matrix(rows)

    # Cross-validated comparison on held-out folds.
    idx = list(range(len(rows)))
    random.Random(seed).shuffle(idx)
    default_pred = [0.0] * len(rows)
    calib_pred = [0.0] * len(rows)
    for f in range(k):
        held = set(idx[f::k])
        train = [i for i in idx if i not in held]
        w = nnls([x[i] for i in train], [y[i] for i in train])
        total = sum(w) or 1.0
        wn = [v / total for v in w]
        for i in held:
            calib_pred[i] = sum(wi * xi for wi, xi in zip(wn, x[i]))
            default_pred[i] = _default_raw(rows[i], spec_weights)
    cv_default = spearman(default_pred, y)
    cv_calib = spearman(calib_pred, y)

    w_all = nnls(x, y)
    total = sum(w_all) or 1.0
    weights = {d: w_all[j] / total for j, d in enumerate(WEIGHTED_DRIVERS)}
    notes = []
    if cv_calib <= cv_default:
        weights = spec_weights
        notes.append("Calibrated weights did not beat the defaults out of fold; defaults kept.")
    scores = [a.score.total for a in rows]
    return Calibration(weights, len(rows), cv_default, cv_calib, fit_logit_scale(scores, y, seed=seed), notes)


def win_probability(score_a: float, score_b: float, logit_scale: float = 12.0) -> float:
    return 1.0 / (1.0 + math.exp(-(score_a - score_b) / logit_scale))
