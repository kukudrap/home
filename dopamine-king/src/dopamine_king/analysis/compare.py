"""Head-to-head comparison of two hooks with an explanation a marketer can act on."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..scoring import HookScore, load_spec, score_hook
from .calibrate import win_probability


@dataclass
class Comparison:
    a: HookScore
    b: HookScore
    p_a_wins: float
    winner: str                           # "a" | "b" | "tie"
    driver_deltas: dict[str, float]       # a minus b, points
    reasons_en: list[str] = field(default_factory=list)
    reasons_cs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "a": self.a.to_dict(), "b": self.b.to_dict(), "p_a_wins": round(self.p_a_wins, 4), "winner": self.winner,
            "driver_deltas": {k: round(v, 2) for k, v in self.driver_deltas.items()},
            "reasons_en": self.reasons_en, "reasons_cs": self.reasons_cs,
        }


def compare_hooks(a: str, b: str, *, lang: str | None = None, logit_scale: float = 12.0, weights: dict | None = None) -> Comparison:
    sa, sb = score_hook(a, lang=lang, weights=weights), score_hook(b, lang=lang, weights=weights)
    p = win_probability(sa.total, sb.total, logit_scale)
    winner = "tie" if abs(sa.total - sb.total) < 2.0 else ("a" if sa.total > sb.total else "b")
    deltas = {k: sa.parts[k] - sb.parts[k] for k in sa.parts}
    labels = load_spec()["labels"]
    reasons_en: list[str] = []
    reasons_cs: list[str] = []
    for key, delta in sorted(deltas.items(), key=lambda kv: -abs(kv[1]))[:3]:
        if abs(delta) < 8:
            continue
        lead = "A" if delta > 0 else "B"
        reasons_en.append(f"{lead} is stronger on {labels[key]['en'].lower()} ({abs(delta):.0f} points).")
        reasons_cs.append(f"{lead} je silnější v oblasti: {labels[key]['cs'].lower()} ({abs(delta):.0f} bodů).")
    for name, s in (("A", sa), ("B", sb)):
        if s.clickbait_risk > 0.35:
            reasons_en.append(f"{name} carries clickbait risk ({s.clickbait_risk:.0%}), which costs trust.")
            reasons_cs.append(f"{name} nese riziko clickbaitu ({s.clickbait_risk:.0%}), což snižuje důvěru.")
    return Comparison(sa, sb, p, winner, deltas, reasons_en, reasons_cs)
