"""Core data models shared by every Dopamine King module.

Plain dataclasses, JSON friendly, standard library only.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field, fields
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Cohorts keep benchmarks fair: a sneaker launch is never compared with a B2B changelog.
COHORT_LABELS: dict[str, dict[str, str]] = {
    "tech": {"en": "Tech", "cs": "Technologie"},
    "b2b-saas": {"en": "B2B SaaS", "cs": "B2B SaaS"},
    "consumer-electronics": {"en": "Consumer electronics", "cs": "Spotřební elektronika"},
    "sport": {"en": "Sport", "cs": "Sport"},
    "fashion-beauty": {"en": "Fashion and beauty", "cs": "Móda a krása"},
    "food-beverage": {"en": "Food and beverage", "cs": "Jídlo a nápoje"},
    "retail-ecommerce": {"en": "Retail and e-commerce", "cs": "Retail a e-commerce"},
    "finance": {"en": "Finance", "cs": "Finance"},
    "travel": {"en": "Travel", "cs": "Cestování"},
    "auto": {"en": "Automotive", "cs": "Auto-moto"},
    "media-entertainment": {"en": "Media and entertainment", "cs": "Média a zábava"},
    "gaming": {"en": "Gaming", "cs": "Hry"},
    "health-wellness": {"en": "Health and wellness", "cs": "Zdraví a wellness"},
    "home-living": {"en": "Home and living", "cs": "Domov a bydlení"},
    "cz-local": {"en": "Czech local brands", "cs": "České značky"},
    # photobiomodulation vertical (see data/verticals/pbm)
    "pbm-home-devices": {"en": "PBM home devices", "cs": "Domácí zařízení (PBM)"},
    "pbm-skin-led": {"en": "Skin and beauty LED", "cs": "LED pro pleť a krásu"},
    "pbm-clinical": {"en": "Clinical and professional PBM", "cs": "Klinická a profesionální PBM"},
    "pbm-recovery-sport": {"en": "Recovery and sport", "cs": "Regenerace a sport"},
    "pbm-science": {"en": "Science and societies", "cs": "Věda a odborné společnosti"},
    "pbm-media": {"en": "Education and review media", "cs": "Vzdělávací a recenzní média"},
    "pbm-cz-sk": {"en": "Czech and Slovak PBM", "cs": "České a slovenské PBM"},
}
COHORTS = tuple(COHORT_LABELS)

PLATFORMS = (
    "blog", "newsroom", "youtube", "instagram", "tiktok", "x", "linkedin", "facebook",
    "threads", "reddit", "email", "ad", "podcast", "web", "other",
)
FORMATS = (
    "article", "post", "thread", "video", "short", "carousel", "email", "ad",
    "press", "landing", "podcast", "headline",
)

_TRACKING_PARAMS = {
    "fbclid", "gclid", "dclid", "msclkid", "yclid", "igshid", "mc_cid", "mc_eid",
    "ref", "ref_src", "_hsenc", "_hsmi", "mkt_tok", "s_cid", "cmpid",
}


def canonical_url(url: str) -> str:
    """Normalise a URL so the same page always maps to the same id."""
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = parts.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS
    )
    return urlunsplit((scheme, host, path, urlencode(query), ""))


def item_id_for_url(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode("utf-8")).hexdigest()[:16]


class Serializable:
    """Mixin giving dataclasses a tolerant dict round trip."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)  # type: ignore[call-overload]

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        names = {f.name for f in fields(cls)}  # type: ignore[arg-type]
        return cls(**{k: v for k, v in data.items() if k in names})


@dataclass
class Brand(Serializable):
    id: str                      # slug, e.g. "hubspot"
    name: str
    cohort: str                  # one of COHORTS
    country: str | None = None   # ISO 3166 alpha-2
    homepage: str | None = None
    # Discovery hints. Everything here is unverified until `kingctl sources verify` ran.
    feeds: list[str] = field(default_factory=list)
    sitemaps: list[str] = field(default_factory=list)
    content_paths: list[str] = field(default_factory=list)  # e.g. ["/blog", "/news"]
    verified: bool = False
    synthetic: bool = False


@dataclass
class ContentItem(Serializable):
    id: str                      # item_id_for_url(url) for real items, "syn-0001" for synthetic
    brand_id: str
    platform: str                # one of PLATFORMS
    format: str                  # one of FORMATS
    title: str
    url: str | None = None
    excerpt: str = ""            # short excerpt only (<= 300 chars), never the full text
    lang: str = "en"
    published_at: str | None = None   # ISO 8601
    word_count: int | None = None
    # Raw performance signals with provenance in the key, e.g. "hn_points", "views", "comments".
    signals: dict[str, float] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    synthetic: bool = False
    fetched_at: str | None = None
