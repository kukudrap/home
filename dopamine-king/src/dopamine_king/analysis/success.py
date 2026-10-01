"""Success Index: a 0..100 performance label that is fair across reach, platform and cohort.

Raw reach is dominated by brand size, so engagement is converted to rates (likes per view, ...)
and every rate is ranked as a percentile inside its own cohort and platform group. The index is
the weighted mean of the available percentiles. Every item keeps the provenance of its signals.
"""
from __future__ import annotations

from typing import Iterable, Mapping

from ..models import ContentItem
from .linalg import percentile_rank

DENOMINATORS = ("views", "impressions", "reach")
RATE_SOURCES = (("like_rate", "likes"), ("comment_rate", "comments"), ("share_rate", "shares"), ("save_rate", "saves"))
PASSTHROUGH = ("ctr", "watch_time", "hn_points", "hn_comments")

SIGNAL_WEIGHTS: dict[str, float] = {
    "like_rate": 1.0, "comment_rate": 1.0, "share_rate": 1.3, "save_rate": 1.3, "ctr": 1.2,
    "watch_time": 1.2, "hn_points": 0.6, "hn_comments": 0.6, "comments_raw": 0.4,
}


def derived_signals(item: ContentItem) -> dict[str, float]:
    s = item.signals
    denom = next((s[k] for k in DENOMINATORS if s.get(k, 0) > 0), None)
    out: dict[str, float] = {}
    if denom:
        for name, num in RATE_SOURCES:
            if num in s:
                out[name] = s[num] / denom
    elif "comments" in s:
        out["comments_raw"] = s["comments"]
    for key in PASSTHROUGH:
        if key in s:
            out[key] = s[key]
    return out


def success_index(
    items: Iterable[ContentItem],
    cohort_by_brand: Mapping[str, str],
    *,
    min_group: int = 15,
    weights: Mapping[str, float] | None = None,
) -> dict[str, float | None]:
    """Returns {item_id: index or None when no usable signal}."""
    weights = dict(SIGNAL_WEIGHTS if weights is None else weights)
    items = list(items)
    derived = {it.id: derived_signals(it) for it in items}
    levels: dict[str, dict[tuple, dict[str, list[float]]]] = {"cp": {}, "c": {}, "all": {}}
    keys_for = {
        "cp": lambda it: (cohort_by_brand.get(it.brand_id), it.platform),
        "c": lambda it: (cohort_by_brand.get(it.brand_id),),
        "all": lambda it: (),
    }
    for it in items:
        for level, keyf in keys_for.items():
            bucket = levels[level].setdefault(keyf(it), {})
            for sig, val in derived[it.id].items():
                bucket.setdefault(sig, []).append(val)
    for level in levels.values():
        for bucket in level.values():
            for sig in bucket:
                bucket[sig].sort()

    result: dict[str, float | None] = {}
    for it in items:
        num = den = 0.0
        for sig, val in derived[it.id].items():
            w = weights.get(sig, 0.0)
            if w <= 0:
                continue
            for level, keyf in keys_for.items():
                pool = levels[level].get(keyf(it), {}).get(sig, [])
                if len(pool) >= min_group or level == "all":
                    if len(pool) >= min_group:
                        num += w * percentile_rank(pool, val)
                        den += w
                    break
        result[it.id] = num / den if den else None
    return result
