"""Audience simulator: a sandbox for experiments when no real traffic exists.

Click-through is modelled as base_ctr * exp(slope * (score - 40)) with a clickbait penalty, then
sampled binomially. It is a simulation, not a prediction: it exists so the Lab and the game can
teach experimentation, and every result it produces is labelled ``simulated``.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from ..scoring import score_hook
from .ab import bayes_ab, two_proportion_test


def binomial(rng: random.Random, n: int, p: float) -> int:
    if p <= 0 or n <= 0:
        return 0
    if p >= 1:
        return n
    var = n * p * (1 - p)
    if var > 25:
        return min(n, max(0, int(round(rng.gauss(n * p, math.sqrt(var))))))
    return sum(1 for _ in range(n) if rng.random() < p)


@dataclass
class VariantOutcome:
    name: str
    text: str
    score: float
    true_ctr: float
    impressions: int
    clicks: int

    @property
    def observed_ctr(self) -> float:
        return self.clicks / self.impressions if self.impressions else 0.0


class AudienceSimulator:
    def __init__(self, base_ctr: float = 0.02, slope: float = 0.018, seed: int = 0) -> None:
        self.base_ctr = base_ctr
        self.slope = slope
        self.rng = random.Random(seed)

    def true_ctr(self, text: str, lang: str | None = None) -> float:
        s = score_hook(text, lang=lang)
        lift = math.exp(self.slope * (s.total - 40.0)) * (1.0 - 0.5 * s.clickbait_risk)
        return min(0.5, self.base_ctr * lift)

    def run(self, variants: dict[str, str], impressions_each: int, lang: str | None = None) -> list[VariantOutcome]:
        out = []
        for name, text in variants.items():
            ctr = self.true_ctr(text, lang)
            out.append(VariantOutcome(name, text, score_hook(text, lang=lang).total, ctr, impressions_each,
                                      binomial(self.rng, impressions_each, ctr)))
        return out

    def duel(self, a: str, b: str, impressions_each: int = 5000, lang: str | None = None) -> dict:
        res = self.run({"A": a, "B": b}, impressions_each, lang)
        ta = two_proportion_test(res[0].clicks, res[0].impressions, res[1].clicks, res[1].impressions)
        bayes = bayes_ab(res[0].clicks, res[0].impressions, res[1].clicks, res[1].impressions, seed=1)
        return {
            "simulated": True,
            "variants": [{"name": r.name, "text": r.text, "score": round(r.score, 2), "true_ctr": round(r.true_ctr, 5),
                          "clicks": r.clicks, "impressions": r.impressions,
                          "observed_ctr": round(r.observed_ctr, 5)} for r in res],
            "frequentist": ta.to_dict(), "bayesian": bayes.to_dict(),
        }
