"""Benchmark: where does a hook stand against the corpus, and what do the winners do differently?"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from ..models import ContentItem
from ..scoring import FEATURE_NAMES, HookScore, score_hook
from .linalg import mean, percentile_rank, quantile
from .success import success_index


@dataclass
class ItemAnalysis:
    item_id: str
    cohort: str
    platform: str
    lang: str
    score: HookScore
    success: float | None


def analyze_items(
    items: Iterable[ContentItem],
    cohort_by_brand: Mapping[str, str],
    *,
    weights: Mapping[str, float] | None = None,
    min_group: int = 15,
) -> list[ItemAnalysis]:
    items = list(items)
    index = success_index(items, cohort_by_brand, min_group=min_group)
    out = []
    for it in items:
        sc = score_hook(it.title, lang=it.lang, weights=dict(weights) if weights else None)
        out.append(ItemAnalysis(it.id, cohort_by_brand.get(it.brand_id, "unknown"), it.platform, it.lang, sc, index[it.id]))
    return out


class Benchmark:
    def __init__(self, analyses: list[ItemAnalysis]) -> None:
        self.analyses = analyses
        self._by_cohort: dict[str | None, list[float]] = {None: sorted(a.score.total for a in analyses)}
        for a in analyses:
            self._by_cohort.setdefault(a.cohort, []).append(a.score.total)
        for k, v in self._by_cohort.items():
            v.sort()

    def cohorts(self) -> list[str]:
        return sorted(k for k in self._by_cohort if k)

    def percentile(self, score: float, cohort: str | None = None) -> float:
        pool = self._by_cohort.get(cohort) or self._by_cohort[None]
        return percentile_rank(pool, score)

    def stats(self, cohort: str | None = None) -> dict[str, float]:
        pool = self._by_cohort.get(cohort) or self._by_cohort[None]
        return {
            "n": float(len(pool)), "mean": mean(pool), "p25": quantile(pool, 0.25),
            "p50": quantile(pool, 0.5), "p75": quantile(pool, 0.75), "p90": quantile(pool, 0.9),
        }

    def top_profile(self, cohort: str | None = None, top_quantile: float = 0.9) -> dict[str, dict[str, float]]:
        """Mean feature values of the top performers versus everyone else (by success index)."""
        rows = [a for a in self.analyses if a.success is not None and (cohort is None or a.cohort == cohort)]
        if len(rows) < 20:
            return {}
        cut = quantile(sorted(a.success for a in rows), top_quantile)  # type: ignore[arg-type]
        top = [a for a in rows if a.success >= cut]  # type: ignore[operator]
        rest = [a for a in rows if a.success < cut]  # type: ignore[operator]
        profile: dict[str, dict[str, float]] = {}
        for name in FEATURE_NAMES:
            t = mean([a.score.features[name] for a in top])
            r = mean([a.score.features[name] for a in rest])
            profile[name] = {"top": t, "rest": r, "delta": t - r}
        return profile

    def compare(self, text: str, *, cohort: str | None = None, lang: str | None = None) -> dict:
        sc = score_hook(text, lang=lang)
        st = self.stats(cohort)
        profile = self.top_profile(cohort)
        gaps = sorted(
            ({"feature": k, "yours": sc.features[k], "top": v["top"], "gap": v["top"] - sc.features[k]}
             for k, v in profile.items() if k in sc.features),
            key=lambda d: -abs(d["gap"]),
        )[:5]
        return {
            "score": sc.total, "percentile": self.percentile(sc.total, cohort),
            "vs_median": sc.total - st["p50"], "vs_p90": sc.total - st["p90"],
            "cohort_stats": st, "feature_gaps": gaps, "clickbait_risk": sc.clickbait_risk,
        }
