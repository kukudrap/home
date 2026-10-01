"""Pattern mining: which hook features go with success, with honest uncertainty."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Sequence

from .benchmark import ItemAnalysis
from .linalg import bootstrap_coef_ci, mean, quantile, ridge_fit

PATTERN_FEATURES = (
    "has_number", "starts_with_number", "is_question", "open_loop", "exclaim", "n_words",
    "curiosity_hits", "contrast_hits", "emotion_hits", "practical_hits", "social_hits",
    "second_person_hits", "clickbait_hits", "overclaim_hits", "negative_hits", "positive_hits",
    "avg_word_len", "caps_ratio",
)

LABELS = {
    "has_number": ("Contains a number", "Obsahuje číslo"),
    "starts_with_number": ("Starts with a number", "Začíná číslem"),
    "is_question": ("Is a question", "Je otázka"),
    "open_loop": ("Open loop (colon or ellipsis)", "Otevřená smyčka (dvojtečka, tři tečky)"),
    "exclaim": ("Exclamation marks", "Vykřičníky"),
    "n_words": ("Length in words", "Délka ve slovech"),
    "curiosity_hits": ("Curiosity phrases", "Fráze vzbuzující zvědavost"),
    "contrast_hits": ("Contrast or myth-busting", "Kontrast a vyvracení mýtů"),
    "emotion_hits": ("Emotion words", "Emoční slova"),
    "practical_hits": ("Practical value words", "Slova praktického užitku"),
    "social_hits": ("Social currency words", "Slova sociální měny"),
    "second_person_hits": ("Addresses the reader", "Oslovuje čtenáře"),
    "clickbait_hits": ("Clickbait phrases", "Clickbaitové fráze"),
    "overclaim_hits": ("Overclaims", "Přehnané sliby"),
    "negative_hits": ("Negative framing", "Negativní rámování"),
    "positive_hits": ("Positive framing", "Pozitivní rámování"),
    "avg_word_len": ("Average word length", "Průměrná délka slova"),
    "caps_ratio": ("ALL CAPS share", "Podíl VELKÝCH PÍSMEN"),
}


@dataclass
class Pattern:
    feature: str
    label_en: str
    label_cs: str
    kind: str                        # "binary" | "numeric"
    n: int
    prevalence: float                # share of items where a binary feature is present (or mean for numeric)
    lift: float                      # success index points: present minus absent (binary) or per +1 SD (numeric)
    lift_ci: tuple[float, float]
    adj_effect: float                # ridge effect per +1 SD, other features held constant (index points)
    adj_ci: tuple[float, float]
    significant: bool                # adjusted interval excludes zero
    examples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "feature": self.feature, "label_en": self.label_en, "label_cs": self.label_cs, "kind": self.kind,
            "n": self.n, "prevalence": round(self.prevalence, 4), "lift": round(self.lift, 3),
            "lift_ci": [round(self.lift_ci[0], 3), round(self.lift_ci[1], 3)],
            "adj_effect": round(self.adj_effect, 3), "adj_ci": [round(self.adj_ci[0], 3), round(self.adj_ci[1], 3)],
            "significant": self.significant, "examples": self.examples,
        }


def _diff_ci(present: list[float], absent: list[float], n_boot: int, seed: int) -> tuple[float, float, float]:
    base = mean(present) - mean(absent)
    if len(present) < 3 or len(absent) < 3:
        return base, base, base
    rng = random.Random(seed)
    draws = []
    for _ in range(n_boot):
        p = [present[rng.randrange(len(present))] for _ in present]
        a = [absent[rng.randrange(len(absent))] for _ in absent]
        draws.append(mean(p) - mean(a))
    draws.sort()
    return base, quantile(draws, 0.025), quantile(draws, 0.975)


def mine_patterns(
    analyses: Sequence[ItemAnalysis],
    titles: dict[str, str] | None = None,
    *,
    cohort: str | None = None,
    features: Sequence[str] = PATTERN_FEATURES,
    lam: float = 5.0,
    n_boot: int = 200,
    seed: int = 1,
    min_n: int = 40,
) -> list[Pattern]:
    rows = [a for a in analyses if a.success is not None and (cohort is None or a.cohort == cohort)]
    if len(rows) < min_n:
        return []
    keep = [f for f in features if len({a.score.features[f] for a in rows}) > 1]
    x = [[a.score.features[f] for f in keep] for a in rows]
    y = [float(a.success) for a in rows]  # type: ignore[arg-type]
    fit = ridge_fit(x, y, lam)
    cis = bootstrap_coef_ci(x, y, lam, n_boot=n_boot, seed=seed)
    out: list[Pattern] = []
    for j, name in enumerate(keep):
        vals = [r[j] for r in x]
        binary = set(vals) <= {0.0, 1.0}
        if binary:
            present = [yy for v, yy in zip(vals, y) if v == 1.0]
            absent = [yy for v, yy in zip(vals, y) if v == 0.0]
            lift, lo, hi = _diff_ci(present, absent, max(60, n_boot // 2), seed + j)
            prevalence = len(present) / len(vals)
        else:
            sd = fit.stds[j]
            lift, lo, hi = fit.coef[j] * sd, cis[j][0], cis[j][1]
            prevalence = mean(vals)
        adj = fit.coef_std[j]
        examples: list[str] = []
        if titles:
            best = sorted(
                (a for a, v in zip(rows, vals) if v > 0),
                key=lambda a: -(a.success or 0.0),
            )[:3]
            examples = [titles[a.item_id] for a in best if a.item_id in titles]
        en, cs = LABELS.get(name, (name, name))
        out.append(Pattern(name, en, cs, "binary" if binary else "numeric", len(rows), prevalence, lift, (lo, hi),
                           adj, cis[j], not (cis[j][0] <= 0.0 <= cis[j][1]), examples))
    out.sort(key=lambda p: -abs(p.adj_effect))
    return out
