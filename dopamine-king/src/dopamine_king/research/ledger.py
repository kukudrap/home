"""The evidence ledger: studies, the links from content tactics to studies, and an honest summary.

The ledger never invents evidence. A tactic without links summarises as "none", and a study only
counts as ``verified`` after ``Ledger.verify`` resolved it against Crossref.
"""
from __future__ import annotations

import difflib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..net import Fetcher
from .crossref import CrossrefClient
from .grading import apply_grade
from .models import (
    CONFIDENCES, DESIGNS, DIRECTIONS, DOI_RE, SOURCES, EvidenceLink, Serializable, Study,
    fold, normalize_doi, normalize_title,
)
from .tactics import TACTICS

LEDGER_VERSION = 1
SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "seed_ledger.json"
GOOD_GRADES = ("A", "B")
VERIFY_TITLE_RATIO = 0.85        # title similarity needed to confirm a DOI
SUGGEST_TITLE_RATIO = 0.92       # stricter bar before a DOI is even suggested
_DIRECTION_ORDER = {d: i for i, d in enumerate(DIRECTIONS)}


@dataclass
class EvidenceSummary(Serializable):
    tactic_id: str
    label: str                       # strong | moderate | limited | contested | none
    grade: str                       # best letter among the linked studies ("" when none)
    n_studies: int
    direction_counts: dict[str, int] = field(default_factory=dict)
    headline_en: str = ""
    headline_cs: str = ""
    caveats_en: list[str] = field(default_factory=list)
    caveats_cs: list[str] = field(default_factory=list)


def _cite(study: Study) -> str:
    """Short in-text citation such as "Berger & Milkman 2012", falling back to the title."""
    surnames = [a.split(",")[0].strip() for a in study.authors if a.strip()]
    year = study.year if study.year is not None else "n.d."
    if not surnames:
        return f"{study.title[:40].rstrip()} ({year})"
    if len(surnames) == 1:
        return f"{surnames[0]} {year}"
    if len(surnames) == 2:
        return f"{surnames[0]} & {surnames[1]} {year}"
    return f"{surnames[0]} et al. {year}"


def _title_match(ours: str, theirs: str, threshold: float, *, allow_prefix: bool = False) -> tuple[bool, float]:
    a, b = normalize_title(ours), normalize_title(theirs)
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    if ratio >= threshold:
        return True, ratio
    short, long_ = sorted((a, b), key=len)
    # one side may lack the subtitle; a long common start is still the same work
    return (allow_prefix and len(short) >= 20 and long_.startswith(short)), ratio


def _headline(label: str, *, sup_ab: int, sup_c: int, con_ab: int, mixed_ab: int, direct: int) -> tuple[str, str]:
    if label == "contested":
        return (
            f"Contested: studies graded A or B point in both directions ({sup_ab} supporting, {con_ab} contradicting).",
            f"Sporné: studie se stupněm A nebo B ukazují oběma směry (podporuje {sup_ab}, odporuje {con_ab}).",
        )
    if label == "strong":
        en = f"Strong evidence: {sup_ab} supporting studies graded A or B, none of that grade contradicts them."
        cs = f"Silné důkazy: podpůrných studií se stupněm A nebo B je {sup_ab}, žádná stejně kvalitní jim neodporuje."
    elif label == "moderate":
        if sup_ab == 1:
            en = "Moderate evidence: one supporting study graded A or B."
            cs = "Střední síla důkazů: podpůrná studie se stupněm A nebo B je jedna."
        else:
            en = f"Moderate evidence: {sup_c} supporting studies graded C."
            cs = f"Střední síla důkazů: podpůrných studií se stupněm C je {sup_c}."
    elif direct == 0:
        return (
            "Limited evidence: only background research is linked, no direct test of this tactic.",
            "Omezené důkazy: je propojen jen podkladový výzkum, žádný přímý test této taktiky.",
        )
    elif con_ab:
        return (
            "Limited evidence: the best linked studies contradict this tactic.",
            "Omezené důkazy: nejkvalitnější propojené studie této taktice odporují.",
        )
    else:
        noun = "study" if direct == 1 else "studies"
        return (
            f"Limited evidence: {direct} linked {noun}, none strong enough to carry the claim.",
            f"Omezené důkazy: propojených studií je {direct}, žádná nestačí k pevnému závěru.",
        )
    if mixed_ab:
        en += f" Studies graded A or B with mixed results: {mixed_ab}."
        cs += f" Studie se stupněm A nebo B se smíšenými výsledky: {mixed_ab}."
    return en, cs


class Ledger:
    def __init__(self, studies: list[Study] | None = None, links: list[EvidenceLink] | None = None) -> None:
        self._studies: dict[str, Study] = {}
        self._links: list[EvidenceLink] = []
        for study in studies or []:
            self.add_study(study)
        for link in links or []:
            self.link(link)

    # -- content --------------------------------------------------------------------
    @property
    def studies(self) -> list[Study]:
        return list(self._studies.values())

    @property
    def links(self) -> list[EvidenceLink]:
        return list(self._links)

    def add_study(self, study: Study) -> None:
        """Add or replace a study (same id). A study without a grade is graded on the way in."""
        if not study.grade:
            apply_grade(study)
        self._studies[study.id] = study

    def link(self, link: EvidenceLink) -> None:
        """Add a link; a second link for the same tactic and study replaces the first."""
        if link.direction not in DIRECTIONS:
            raise ValueError(f"direction must be one of {DIRECTIONS}, got {link.direction!r}")
        for i, existing in enumerate(self._links):
            if existing.tactic_id == link.tactic_id and existing.study_id == link.study_id:
                self._links[i] = link
                return
        self._links.append(link)

    def get_study(self, study_id: str) -> Study | None:
        return self._studies.get(study_id)

    def regrade(self, *, today_year: int | None = None) -> None:
        """Recompute every grade, for example after citation counts changed."""
        for study in self._studies.values():
            apply_grade(study, today_year=today_year)

    # -- evidence -------------------------------------------------------------------
    def evidence_for(self, tactic_id: str) -> list[tuple[Study, EvidenceLink]]:
        pairs = [
            (self._studies[link.study_id], link)
            for link in self._links
            if link.tactic_id == tactic_id and link.study_id in self._studies
        ]
        pairs.sort(key=lambda p: (
            -p[0].grade_score, _DIRECTION_ORDER.get(p[1].direction, 9), -(p[0].year or 0), p[0].title.lower(),
        ))
        return pairs

    def summary(self, tactic_id: str) -> EvidenceSummary:
        pairs = self.evidence_for(tactic_id)
        counts = {d: 0 for d in DIRECTIONS}
        for _, link in pairs:
            counts[link.direction] += 1
        if not pairs:
            return EvidenceSummary(
                tactic_id, "none", "", 0, counts,
                "No evidence linked yet.", "Zatím žádné propojené důkazy.",
            )

        def graded(direction: str, letters: tuple[str, ...]) -> int:
            return sum(1 for s, link in pairs if link.direction == direction and s.grade in letters and not s.retracted)

        sup_ab = graded("supports", GOOD_GRADES)
        sup_c = graded("supports", ("C",))
        con_ab = graded("contradicts", GOOD_GRADES)
        mixed_ab = graded("mixed", GOOD_GRADES)
        direct = counts["supports"] + counts["mixed"] + counts["contradicts"]
        if sup_ab and con_ab:
            label = "contested"
        elif con_ab:
            label = "limited"        # the best studies contradict the claim; nothing strong backs it
        elif sup_ab >= 2:
            label = "strong"
        elif sup_ab == 1 or sup_c >= 2:
            label = "moderate"
        else:
            label = "limited"
        en, cs = _headline(label, sup_ab=sup_ab, sup_c=sup_c, con_ab=con_ab, mixed_ab=mixed_ab, direct=direct)

        relevant = [s for s, link in pairs if link.direction != "context"] or [s for s, _ in pairs]
        best = min((s.grade or "D") for s in relevant)
        caveats_en: list[str] = []
        caveats_cs: list[str] = []
        for study, link in pairs:
            if link.caveat_en and (text := f"{_cite(study)}: {link.caveat_en}") not in caveats_en:
                caveats_en.append(text)
            if link.caveat_cs and (text := f"{_cite(study)}: {link.caveat_cs}") not in caveats_cs:
                caveats_cs.append(text)
        if any(s.retracted for s, _ in pairs):
            caveats_en.append("A linked study has been retracted and is not counted.")
            caveats_cs.append("Propojená studie byla stažena a nezapočítává se.")
        return EvidenceSummary(
            tactic_id, label, best, len({s.id for s, _ in pairs}), counts, en, cs, caveats_en, caveats_cs,
        )

    def search_text(self, text: str) -> list[Study]:
        """Studies matching every word of ``text`` in title, authors, abstract or link notes."""
        words = fold(text).split()
        if not words:
            return []
        notes: dict[str, list[str]] = {}
        for link in self._links:
            notes.setdefault(link.study_id, []).extend(
                [link.note_en, link.note_cs, link.caveat_en, link.caveat_cs]
            )
        hits = []
        for study in self._studies.values():
            haystack = fold(" ".join(
                [study.title, " ".join(study.authors), study.abstract or "", *notes.get(study.id, [])]
            ))
            if all(word in haystack for word in words):
                hits.append(study)
        hits.sort(key=lambda s: (-s.grade_score, -(s.year or 0), s.title.lower()))
        return hits

    # -- integrity ------------------------------------------------------------------
    def validate(self) -> list[str]:
        """Structural problems: dangling links, unknown tactics, bad enums, malformed DOIs."""
        problems: list[str] = []
        for study in self._studies.values():
            if study.design not in DESIGNS:
                problems.append(f"{study.id}: unknown design {study.design!r}")
            if study.source not in SOURCES:
                problems.append(f"{study.id}: unknown source {study.source!r}")
            if study.confidence not in CONFIDENCES:
                problems.append(f"{study.id}: unknown confidence {study.confidence!r}")
            if study.doi and not DOI_RE.match(study.doi):
                problems.append(f"{study.id}: malformed doi {study.doi!r}")
            if study.doi and study.id != f"doi:{study.doi.lower()}" and not study.id.startswith("arxiv:"):
                problems.append(f"{study.id}: id does not match doi {study.doi!r}")
        for link in self._links:
            if link.study_id not in self._studies:
                problems.append(f"link {link.tactic_id} -> {link.study_id}: unknown study")
            if link.tactic_id not in TACTICS:
                problems.append(f"link {link.tactic_id} -> {link.study_id}: unknown tactic")
            if not (link.note_en and link.note_cs):
                problems.append(f"link {link.tactic_id} -> {link.study_id}: note missing in a language")
        if "—" in json.dumps(self.to_dict(), ensure_ascii=False):
            problems.append("the long dash character is not allowed anywhere in the ledger")
        return problems

    def verify(self, fetcher: Fetcher, *, mailto: str | None = None) -> list[dict[str, Any]]:
        """Check every study against Crossref. Never changes a DOI; network errors change nothing.

        With a DOI: the Crossref record must match the title (similarity >= 0.85) and one of its
        publication years. Without a DOI: a DOI is only suggested (in ``verification_note``) when
        exactly one Crossref result matches the title (>= 0.92) and the year.
        """
        client = CrossrefClient(fetcher, mailto)
        results: list[dict[str, Any]] = []
        for study in self.studies:
            try:
                results.append(self._verify_one(client, study))
            except Exception as err:  # noqa: BLE001 - report it, keep the other studies going
                results.append({"study_id": study.id, "status": "error", "detail": f"{type(err).__name__}: {err}"})
        return results

    def _verify_one(self, client: CrossrefClient, study: Study) -> dict[str, Any]:
        if study.doi:
            return self._verify_doi(client, study)
        return self._suggest_doi(client, study)

    @staticmethod
    def _verify_doi(client: CrossrefClient, study: Study) -> dict[str, Any]:
        def done(status: str, verified: bool, note: str) -> dict[str, Any]:
            study.verified, study.verification_note = verified, note
            return {"study_id": study.id, "status": status, "detail": note}

        if not normalize_doi(study.doi):
            return done("mismatch", False, f"The DOI {study.doi!r} is not well formed.")
        found = client.lookup(study.doi)
        if found is None:
            return done("not_found", False, "DOI not found in Crossref (it may be registered with another agency).")
        record, years = found
        title_ok, ratio = _title_match(study.title, record.title, VERIFY_TITLE_RATIO, allow_prefix=True)
        year_ok = study.year is None or not years or study.year in years
        if title_ok and year_ok:
            note = "Crossref confirms the DOI, title and year."
            if record.retracted:
                study.retracted = True
                apply_grade(study)
                note += " Crossref lists a retraction or withdrawal for this work."
            return done("verified", True, note)
        problems = []
        if not title_ok:
            problems.append(f"title differs (similarity {ratio:.2f}), Crossref has '{record.title}'")
        if not year_ok:
            problems.append(f"year differs, ledger {study.year} but Crossref lists {sorted(years)}")
        return done("mismatch", False, "Crossref mismatch: " + "; ".join(problems) + ".")

    @staticmethod
    def _suggest_doi(client: CrossrefClient, study: Study) -> dict[str, Any]:
        matches = []
        for record, years in client.search_detailed(study.title, rows=5):
            ok, ratio = _title_match(study.title, record.title, SUGGEST_TITLE_RATIO)
            if ok and study.year is not None and study.year in years:
                matches.append((record, ratio))
        if len(matches) == 1:
            record, ratio = matches[0]
            note = (
                f"Suggested DOI {record.doi} (Crossref title similarity {ratio:.2f}, year {study.year}). "
                "Not applied: check it against the source and set the doi field by hand."
            )
            status = "suggestion"
        elif matches:
            note = f"{len(matches)} Crossref records match this title and year; no DOI suggested."
            status = "not_found"
        else:
            note = "No DOI on record and no unambiguous Crossref match by title and year."
            status = "not_found"
        study.verified, study.verification_note = False, note
        return {"study_id": study.id, "status": status, "detail": note}

    def stats(self) -> dict[str, Any]:
        def tally(values: list[str]) -> dict[str, int]:
            out: dict[str, int] = {}
            for value in values:
                out[value] = out.get(value, 0) + 1
            return dict(sorted(out.items()))

        studies = self.studies
        verified = sum(1 for s in studies if s.verified)
        return {
            "studies": len(studies),
            "links": len(self._links),
            "tactics_linked": len({link.tactic_id for link in self._links}),
            "by_design": tally([s.design for s in studies]),
            "by_grade": tally([s.grade or "ungraded" for s in studies]),
            "by_source": tally([s.source for s in studies]),
            "verified": verified,
            "unverified": len(studies) - verified,
            "retracted": sum(1 for s in studies if s.retracted),
        }

    # -- persistence ----------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "version": LEDGER_VERSION,
            "studies": [s.to_dict() for s in self._studies.values()],
            "links": [link.to_dict() for link in self._links],
        }

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, target)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Ledger":
        source = Path(path) if path is not None else SEED_PATH
        data = json.loads(source.read_text(encoding="utf-8"))
        version = data.get("version", LEDGER_VERSION)
        if not isinstance(version, int) or version > LEDGER_VERSION:
            raise ValueError(f"unsupported ledger version {version!r} in {source}")
        studies = [Study.from_dict(d) for d in data.get("studies", [])]
        ids = [s.id for s in studies]
        if len(ids) != len(set(ids)):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"duplicate study ids in {source}: {dupes}")
        return cls(studies, [EvidenceLink.from_dict(d) for d in data.get("links", [])])
