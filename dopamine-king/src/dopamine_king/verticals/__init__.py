"""Verticals: data driven profiles that adapt the generic engine to one industry.

A vertical is a folder under ``data/verticals/<id>/`` with JSON files: ``vertical.json`` (names, cohorts,
glossary, Czech topic forms), ``brands.json`` (the registry for the scraper), ``claims.json`` and
``guard.json`` (the claims profile of the Trust Shield), ``ledger.json`` (studies linked to the claim
topics), ``myths.json``, ``synth.json`` (fictional demo corpus), ``briefs.json`` and ``strategy.json``.
The generic engine never needs to know which vertical it serves; the first one is photobiomodulation
(``pbm``), shipped as the MITO LIGHT edition.
"""
from __future__ import annotations

import functools
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "verticals"
LABEL_RANK = {"none": 0, "limited": 1, "contested": 1, "moderate": 2, "strong": 3}


class VerticalError(ValueError):
    """The vertical does not exist or its files are broken."""


@dataclass
class Vertical:
    id: str
    meta: dict[str, Any]
    path: Path
    _cache: dict[str, Any] = field(default_factory=dict, repr=False)

    # -- names -----------------------------------------------------------------------------------
    def name(self, lang: str = "en") -> str:
        return self.meta.get(f"name_{lang}") or self.meta["name_en"]

    @property
    def claims_profile(self) -> str:
        return self.meta.get("claims_profile", "general")

    @property
    def cohorts(self) -> dict[str, dict[str, str]]:
        return dict(self.meta.get("cohorts", {}))

    @property
    def default_brand(self) -> str | None:
        return self.meta.get("default_brand")

    def public_meta(self) -> dict[str, Any]:
        """What the game needs to describe the vertical (no large tables)."""
        keys = ("id", "name_en", "name_cs", "short_en", "short_cs", "tagline_en", "tagline_cs", "edition_en", "edition_cs",
                "default_brand", "claims_profile", "languages", "cohorts", "glossary", "regulatory_note_en", "regulatory_note_cs")
        return {k: self.meta[k] for k in keys if k in self.meta}

    # -- files -----------------------------------------------------------------------------------
    def _json(self, name: str, default: Any = None) -> Any:
        if name not in self._cache:
            path = self.path / name
            if not path.exists():
                if default is not None:
                    return default
                raise VerticalError(f"vertical {self.id!r} has no {name}")
            try:
                self._cache[name] = json.loads(path.read_text("utf-8"))
            except json.JSONDecodeError as err:
                raise VerticalError(f"{path} is not valid JSON: {err}") from err
        return self._cache[name]

    def claims(self) -> dict[str, Any]:
        return self._json("claims.json")

    def guard(self) -> dict[str, Any]:
        return self._json("guard.json")

    def strategy(self) -> dict[str, Any]:
        return self._json("strategy.json", {})

    def myths(self) -> list[dict[str, Any]]:
        return list(self._json("myths.json", {"myths": []}).get("myths", []))

    def synth(self) -> dict[str, Any]:
        return self._json("synth.json", {})

    def writer_rules(self, lang: str = "en") -> list[str]:
        return list(self.guard().get("writer_rules", {}).get(lang, []))

    def safety_footer(self, lang: str = "en") -> str:
        return str(self.guard().get("safety_footer", {}).get(lang, ""))

    # -- objects ---------------------------------------------------------------------------------
    def brands(self) -> list[Any]:
        from ..models import Brand
        return [Brand.from_dict(b) for b in self._json("brands.json", {"brands": []}).get("brands", [])]

    def bosses(self) -> list[dict[str, Any]]:
        return list(self._json("bosses.json", {"bosses": []}).get("bosses", []))

    def demo_formats(self) -> tuple[str, ...]:
        return tuple(self._json("briefs.json", {}).get("demo_formats", ()))

    def briefs(self, ledger: Any = None) -> dict[str, Any]:
        """Sample briefs. Their ``sources`` are short ids resolved against the ledger: only VERIFIED studies become vetted sources."""
        from ..generate.types import Brief
        data = self._json("briefs.json", {"briefs": []})
        ledger = ledger or self.ledger()
        ids, claims = data.get("source_ids", {}), data.get("source_claims", {})
        out = {}
        for raw in data.get("briefs", []):
            fields = dict(raw)
            key = fields.pop("id")
            sources = []
            for short in fields.pop("sources", []):
                study = ledger.get_study(ids.get(short, ""))
                if study is None or not study.verified:
                    continue
                claim = claims.get(short, {}).get(fields.get("lang", "en")) or claims.get(short, {}).get("en", "")
                sources.append({"id": short, "title": study.title, "url": study.url or "", "claim": claim})
            out[key] = Brief.from_dict({**fields, "sources": sources})
        return out

    def personas(self) -> list[dict[str, Any]]:
        """Target groups of the default brand: who they are, what may be said, what never, how careful the content must be (risk)."""
        return list(self._json("personas.json", {}).get("personas", []))

    def persona_briefs(self, ledger: Any = None) -> dict[str, Any]:
        """One sample brief per persona (``<base>-<persona>-cs``): the base brief with the persona's topic, audience, keywords and care.

        The persona's care and its never-list go into the voice notes, so the writer sees them next to the rules of the profile.
        """
        from ..generate.types import Brief
        data = self._json("personas.json", {})
        base_id = data.get("base", "mito-light-cs")
        base = self.briefs(ledger)[base_id]
        stem = base_id.rsplit("-", 1)[0]
        out = {}
        for persona in data.get("personas", []):
            brief = Brief.from_dict({**base.to_dict(), **persona.get("brief", {})})
            brief.voice_notes = (f"{base.voice_notes} Cílová skupina: {persona['name_cs']}. {persona['care_cs']} "
                                 f"Nikdy: {' '.join(persona.get('never_cs', []))}").strip()
            out[f"{stem}-{persona['id']}-{base.lang}"] = brief
        return out

    def brand_profile(self) -> dict[str, Any]:
        """What public sources say about the default brand (facts with source and confidence, open questions, tone)."""
        return self._json("mito_light.json", {})

    def tactics(self) -> list[Any]:
        """The claim topics as tactics (driver ``claim``), so the evidence ledger can link studies to them."""
        from ..research.models import Tactic
        out = []
        for t in self.claims()["topics"]:
            out.append(Tactic(
                id=t["id"], name_en=t["name_en"], name_cs=t["name_cs"], summary_en=t["claim_en"], summary_cs=t["claim_cs"],
                driver="claim", ethics_en=self.claims()["classes"][t["class"]]["en"], ethics_cs=self.claims()["classes"][t["class"]]["cs"],
            ))
        return out

    def ledger(self, *, include_base: bool = True) -> Any:
        """The study ledger: the general seed (optional) plus the vertical's own studies and links."""
        from ..research.ledger import Ledger
        tactics = {t.id: t for t in self.tactics()}
        ledger = Ledger.load(tactics=tactics) if include_base else Ledger(tactics=tactics)
        path = self.path / "ledger.json"
        if path.exists():
            ledger.absorb(Ledger.load(path, tactics=tactics))
        return ledger

    def claim_map(self, ledger: Any = None) -> list[dict[str, Any]]:
        """Per claim topic: class, wording, evidence label and the studies behind it.

        The label counts only VERIFIED studies, so a bibliographic record nobody has checked can never raise it,
        and it never exceeds the curated cap of the topic. Unverified links are listed as pending.
        """
        from ..research.ledger import Ledger

        ledger = ledger or self.ledger()
        verified_ids = {s.id for s in ledger.studies if s.verified}
        checked = Ledger([s for s in ledger.studies if s.verified],
                         [link for link in ledger.links if link.study_id in verified_ids], ledger.tactics)
        out = []
        for t in self.claims()["topics"]:
            summary = checked.summary(t["id"])
            cap = t.get("label_cap", "none")
            label, capped = summary.label, False
            if summary.label != "contested" and LABEL_RANK.get(summary.label, 0) > LABEL_RANK.get(cap, 0):
                label, capped = cap, True
            pairs = ledger.evidence_for(t["id"])
            pending = sorted({s.id for s, _ in pairs if not s.verified})
            supporters = [s.grade or "D" for s, link in checked.evidence_for(t["id"]) if link.direction == "supports"]
            headline_en, headline_cs = summary.headline_en, summary.headline_cs
            if summary.n_studies == 0 and pending:
                headline_en = f"{len(pending)} linked study(ies) await verification and are not counted yet."
                headline_cs = f"Počet propojených studií čekajících na ověření: {len(pending)}. Zatím se nezapočítávají."
            out.append({
                "id": t["id"], "class": t["class"], "domain": t["domain"],
                "name_en": t["name_en"], "name_cs": t["name_cs"], "claim_en": t["claim_en"], "claim_cs": t["claim_cs"],
                "summary_en": t.get("summary_en", ""), "summary_cs": t.get("summary_cs", ""),
                "safe_en": t.get("safe_en", []), "safe_cs": t.get("safe_cs", []),
                "avoid_en": t.get("avoid_en", []), "avoid_cs": t.get("avoid_cs", []),
                "label": label, "computed_label": summary.label, "capped": capped,
                "cap_reason_en": t.get("cap_reason_en", ""), "cap_reason_cs": t.get("cap_reason_cs", ""),
                "grade": min(supporters, default=""), "n_studies": summary.n_studies, "n_pending": len(pending),
                "direction_counts": summary.direction_counts,
                "headline_en": headline_en, "headline_cs": headline_cs,
                "caveats_en": summary.caveats_en, "caveats_cs": summary.caveats_cs,
                "study_ids": [s.id for s, _ in pairs],
            })
        return out

    def claim_rules(self) -> dict[str, Any]:
        """Everything a client needs to run the claims profile on its own (the game ships it to the browser)."""
        guard = self.guard()
        keys = ("treatment_verbs", "benefit_verbs", "disease_terms", "device_words", "indication_prepositions",
                "regulated_status", "safety_absolute", "therapy_words", "hedge_words", "negation_words",
                "negated_verb_stems", "timeline_patterns", "dose_patterns", "dose_context", "safety_terms", "long_form_formats",
                "masking_phrases", "targeting_phrases", "clause_breakers", "medication_patterns", "strong_claims", "approved_terms")
        topics = [{k: t.get(k) for k in ("id", "class", "name_en", "name_cs", "nouns_en", "nouns_cs", "patterns", "safe_en", "safe_cs", "label_cap")}
                  for t in self.claims()["topics"]]
        return {"profile": guard.get("profile", "wellness"), "topics": topics, **{k: guard[k] for k in keys if k in guard}}


def list_verticals() -> list[str]:
    return sorted(p.name for p in DATA_DIR.iterdir() if (p / "vertical.json").exists()) if DATA_DIR.exists() else []


@functools.lru_cache(maxsize=8)
def load_vertical(vertical_id: str) -> Vertical:
    path = DATA_DIR / vertical_id
    if not (path / "vertical.json").exists():
        raise VerticalError(f"unknown vertical {vertical_id!r}; available: {', '.join(list_verticals()) or 'none'}")
    meta = json.loads((path / "vertical.json").read_text("utf-8"))
    if meta.get("id") != vertical_id:
        raise VerticalError(f"{path / 'vertical.json'} has id {meta.get('id')!r}, expected {vertical_id!r}")
    return Vertical(vertical_id, meta, path)
