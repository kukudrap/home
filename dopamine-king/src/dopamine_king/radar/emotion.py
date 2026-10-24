"""Emotional and experiential claims for the brand, checked by the same Trust Shield as every other text.

The claims live in ``radar/claims_emotional.json``. They are built on levers that have evidence in the study ledger (anticipation, cues,
surprise, story, emotion, belonging, choice) and never state an effect on the body, mood or hormones. A claim that rests on a fact says which
one, and the fact must come from the brand file. Nothing is scored with a made-up number: the strength of a lever is the evidence label of its
tactic in the ledger, and a single sentence is a hypothesis to test.
"""
from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence

from ..generate.guard import TrustShield
from ..generate.types import Brief

IGNORED = {"AI_DISCLOSURE_REMINDER", "HUMAN_REVIEW_REQUIRED", "THERAPY_WORD"}
NUMBER_WORDS = ("jedna", "jeden", "jedno", "dva", "dvě", "tři", "čtyři", "pět", "šest", "sedm", "osm", "devět", "deset", "sto", "tisíc")
SUPERLATIVES = ("nejlepší", "nejvýkonnější", "nejúčinnější", "nejprodávanější", "nejoblíbenější", "lídr", "jediný", "jediná", "jediné", "první v", "číslo jedna")
USES = ("tagline", "headline", "hook", "caption", "microcopy", "ugc")
LABEL_RANK = {"none": 0, "limited": 1, "contested": 1, "moderate": 2, "strong": 3}
GENERAL_USES = ("headline", "hook", "caption", "ugc")         # the other two uses have a list of their own


def load(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text("utf-8"))


def claim_text(item: dict[str, Any]) -> str:
    return item["text"]


def has_number(text: str) -> bool:
    words = {w.lower() for w in re.findall(r"\w+", text)}
    return bool(re.search(r"\d", text)) or any(n in words for n in NUMBER_WORDS)


def brief_for(base: Brief, data: dict[str, Any], item: dict[str, Any]) -> Brief:
    """The brief of the brand with the facts the claim rests on added, so a claim is only judged against what the brand may state."""
    extra = [data["facts"][k]["text"] for k in item.get("support", [])]
    return replace(base, facts=list(base.facts) + extra)


def judge(shield: TrustShield, text: str, brief: Brief) -> dict[str, list[str]]:
    issues = [i for i in shield.check(text, brief) if i.code not in IGNORED]
    return {"errors": sorted({i.code for i in issues if i.severity == "error"}),
            "warnings": sorted({i.code for i in issues if i.severity == "warn"})}


def check_claims(data: dict[str, Any], vertical: Any, ledger: Any) -> dict[str, dict[str, list[str]]]:
    """Trust Shield result per claim id: error codes and warning codes (information notes are left out)."""
    base = vertical.briefs(ledger)["mito-light-cs"]
    shield = TrustShield(ledger)
    return {c["id"]: judge(shield, c["text"], brief_for(base, data, c)) for c in data["claims"]}


def check_forbidden(data: dict[str, Any], vertical: Any, ledger: Any) -> list[dict[str, Any]]:
    """What the shield says about each wording a brand must not use, and about the wording that replaces it."""
    base = vertical.briefs(ledger)["mito-light-cs"]
    shield = TrustShield(ledger)
    rows = []
    for f in data["forbidden"]:
        verdict = judge(shield, f["text"], base)
        rows.append({**f, "found": sorted(set(verdict["errors"]) | set(verdict["warnings"])), "errors": verdict["errors"],
                     "swap_verdict": judge(shield, f["swap"], base)})
    return rows


def registry_corpus(vertical: Any) -> str:
    """Every fact of the brand file and of the sample briefs, as one text the supporting facts must be found in."""
    registry = json.loads((vertical.path / "mito_light.json").read_text("utf-8"))
    briefs = (vertical.path / "briefs.json").read_text("utf-8")
    return " ".join(f["fact_cs"] for f in registry["facts"]) + " " + briefs


def facts_problems(data: dict[str, Any], vertical: Any) -> list[str]:
    corpus = registry_corpus(vertical)
    return [key for key, fact in data["facts"].items() if fact["registry"] not in corpus]


def verified_studies(ledger: Any, tactic_id: str) -> list[dict[str, Any]]:
    """The studies of a tactic whose title, journal and year were found in a public source. The others are left out of every count."""
    return [{"title": s.title, "year": s.year, "grade": s.grade, "direction": link.direction, "note": link.note_cs,
             "url": s.url or (f"https://doi.org/{s.doi}" if s.doi else "")}
            for s, link in ledger.evidence_for(tactic_id) if s.verified]


def lever_evidence(lever: dict[str, Any], ledger: Any) -> list[dict[str, Any]]:
    out = []
    for tid in lever["tactics"]:
        tactic, summary = ledger.tactics[tid], ledger.summary(tid)
        studies = verified_studies(ledger, tid)
        out.append({"id": tid, "name": tactic.name_cs, "label": summary.label, "n_verified": len(studies), "headline": summary.headline_cs,
                    "ethics": tactic.ethics_cs, "studies": studies})
    return out


def lever_summary(evidence: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """A lever is as strong as its weakest tactic. The evidence is for the general idea (for example anticipation), not for a sentence or a product."""
    label = min((e["label"] for e in evidence), key=LABEL_RANK.__getitem__, default="none")
    return {"label": label, "n_verified": len({s["url"] or s["title"] for e in evidence for s in e["studies"]})}


def dopamine_block(ledger: Any) -> dict[str, Any]:
    tactic, summary = ledger.tactics["dopamine-myth"], ledger.summary("dopamine-myth")
    studies = verified_studies(ledger, "dopamine-myth")
    return {"summary": tactic.summary_cs, "ethics": tactic.ethics_cs, "label": summary.label, "n_verified": len(studies), "studies": studies}


def needs_list(claims: Sequence[dict[str, Any]], naming: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """What the brand must confirm before use, each request once, with the texts it concerns."""
    out: dict[str, list[str]] = {}
    for c in claims:
        if c.get("needs"):
            out.setdefault(c["needs"], []).append(c["text"])
    for n in naming:
        if n.get("needs"):
            out.setdefault(n["needs"], []).append(f"Název {n['name']}")
    return [{"need": need, "texts": texts} for need, texts in out.items()]


def section_data(data: dict[str, Any], vertical: Any, ledger: Any, personas: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Everything the report page shows about the claims, with the shield's verdict on each one."""
    verdicts = check_claims(data, vertical, ledger)
    facts = data["facts"]
    claims = []
    for c in data["claims"]:
        claims.append({**c, "verdict": verdicts[c["id"]], "facts": [facts[k]["text"] for k in c.get("support", [])]})
    general = [c for c in claims if not c.get("personas") and c["use"] in GENERAL_USES]
    levers = []
    for lv in data["levers"]:
        evidence = lever_evidence(lv, ledger)
        levers.append({**lv, "evidence": evidence, **lever_summary(evidence), "claims": [c for c in general if c["lever"] == lv["id"]]})
    by_id = {c["id"]: c for c in claims}
    names = {lv["id"]: lv["name_cs"] for lv in data["levers"]}
    return {
        "note": data["note"], "uses": data["uses"], "claims": claims, "levers": levers, "picks": [c for c in claims if c.get("pick")],
        "personas": [{"id": p["id"], "name": p["name_cs"], "risk": p.get("risk", ""), "claims": [c for c in claims if p["id"] in c.get("personas", [])]} for p in personas],
        "taglines": [c for c in claims if c["use"] == "tagline" and not c.get("personas")],
        "microcopy": [c for c in claims if c["use"] == "microcopy" and not c.get("personas")], "lever_names": names,
        "story": [{**s, "facts": [facts[k]["text"] for k in s.get("support", [])]} for s in data["story"]],
        "naming": [{**n, "facts": [facts[k]["text"] for k in n.get("support", [])]} for n in data["naming"]],
        "guardrails": [{**g, "evidence": (lever_evidence({"tactics": [g["tactic"]]}, ledger) if g.get("tactic") else [])} for g in data["guardrails"]],
        "forbidden": check_forbidden(data, vertical, ledger),
        "tests": [{**t, "a_text": by_id[t["a"]]["text"], "b_text": by_id[t["b"]]["text"]} for t in data["tests"]],
        "dopamine": dopamine_block(ledger),
        "needs": needs_list(claims, data["naming"]),
        "totals": {"claims": len(claims), "picks": sum(bool(c.get("pick")) for c in claims), "concepts": sum(bool(c.get("concept")) for c in claims),
                   "errors": sum(len(v["errors"]) for v in verdicts.values()), "warnings": sum(len(v["warnings"]) for v in verdicts.values())},
    }
