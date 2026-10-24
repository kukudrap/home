"""Texts for the actions of the radar, written by the same writers and checked by the same Trust Shield as all other content.

The spec (``radar/drafts.json``) lists a few pages with the facts they may state, plus one post per persona. Nothing is invented
here: facts come from the spec, evidence from the verified studies of the ledger, and every text gets the shield's verdict.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Sequence

from ..generate.packs import build_pack
from ..generate.types import Brief, Writer
from ..scoring import fold

NUMBER_WORDS = {"dva": 2, "dve": 2, "tri": 3, "ctyri": 4, "pet": 5, "sest": 6, "sedm": 7, "osm": 8, "devet": 9, "deset": 10}
HOOK_COUNT = re.compile(r"\b(\d+|" + "|".join(NUMBER_WORDS) + r")\s+(?:\w+\s+){0,2}?(?:parametr|bod|vec|chyb|otazk|tip|krok|duvod|pravid|zpusob)\w*")


def draft_jobs(vertical: Any, spec: dict[str, Any], ledger: Any, *, only: Sequence[str] | None = None) -> list[dict[str, Any]]:
    """One job per page and per persona post: id, kind, title, formats, brief."""
    base = vertical.briefs(ledger)["mito-light-cs"]
    jobs: list[dict[str, Any]] = []
    for page in spec["pages"]:
        brief = replace(base, topic=page["topic"], audience=page["audience"], keyword=page["keyword"],
                        secondary_keywords=list(page["secondary_keywords"]), cta=page["cta"], facts=list(page["facts"]), topic_forms={},
                        sources=[] if page.get("no_sources") else base.sources)
        jobs.append({"id": page["id"], "kind": "page", "action": page.get("action", ""), "title": page["title"], "formats": list(page["formats"]),
                     "brief": brief, "needs_approval": page.get("needs_approval", "")})
    personas = vertical.persona_briefs(ledger)
    meta = {p["id"]: p for p in vertical.personas()}
    for pid in spec["posts"]["personas"]:
        brief = personas[f"mito-light-{pid}-cs"]
        jobs.append({"id": f"post-{pid}", "kind": "post", "action": "persona", "persona": pid, "title": meta[pid].get("name_cs", pid),
                     "formats": list(spec["posts"]["formats"]), "brief": brief, "needs_approval": ""})
    return [j for j in jobs if not only or j["id"] in only]


def run_jobs(jobs: Sequence[dict[str, Any]], writer_factory: Callable[[], Writer], ledger: Any, out_dir: str | Path, *, workers: int = 3,
             log: Callable[[str], None] = print) -> list[dict[str, Any]]:
    """Build and save one pack per job; the index lists verdicts and counts so the report can show them."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    def one(job: dict[str, Any]) -> dict[str, Any]:
        pack = build_pack(job["brief"], job["formats"], writer=writer_factory(), ledger=ledger)
        pack.save(out / job["id"])
        item = pack.items[0] if pack.items else None
        row = {"id": job["id"], "kind": job["kind"], "action": job["action"], "title": job["title"], "persona": job.get("persona", ""),
               "formats": job["formats"], "writer": pack.writer, "needs_approval": job["needs_approval"],
               "verdict": item.verdict if item else "missing",
               "errors": sum(i["severity"] == "error" for i in item.issues) if item else 0,
               "warnings": sum(i["severity"] == "warn" for i in item.issues) if item else 0,
               "open_slots": len(item.slots_open) if item else 0, "created": pack.created}
        log(f"{job['id']}: {row['verdict']} ({row['errors']} errors, {row['warnings']} warnings)")
        return row

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        rows = list(pool.map(one, jobs))
    index_path = out / "index.json"
    kept = json.loads(index_path.read_text("utf-8")) if index_path.exists() else []
    merged = {r["id"]: r for r in kept}                 # a partial run (--only) updates its drafts and keeps the others
    merged.update({r["id"]: r for r in rows})
    index_path.write_text(json.dumps(list(merged.values()), ensure_ascii=False, indent=1) + "\n", "utf-8")
    return rows


def count_mismatch(hook: str, body: str) -> str:
    """"3 parametry" in the hook and four numbered points in the text: the hook promises a count the text does not keep."""
    match = HOOK_COUNT.search(fold(hook.lower()))
    items = [int(m.group(1)) for m in re.finditer(r"^\s*(\d+)[.)]\s", body, flags=re.M)]
    if not match or not items:
        return ""
    promised = int(match.group(1)) if match.group(1).isdigit() else NUMBER_WORDS[match.group(1)]
    return f"Nadpis slibuje {promised}, text má očíslovaných bodů {max(items)}." if promised != max(items) else ""


def load_drafts(folder: str | Path, pack: Any = None) -> list[dict[str, Any]]:
    """The saved drafts with their text, hook, verdict and the shield's remarks, ready for the report."""
    root = Path(folder)
    index = json.loads((root / "index.json").read_text("utf-8"))
    out = []
    for row in index:
        data = json.loads((root / row["id"] / "pack.json").read_text("utf-8"))
        item = data["items"][0]
        from ..generate.seo import render_citations
        issues = [{"severity": i["severity"], "code": i["code"], "message": i["message"]} for i in item["issues"]]
        mismatch = count_mismatch(item["hook"], item["body"])
        if mismatch:
            issues.append({"severity": "warn", "code": "COUNT_MISMATCH", "message": mismatch})
        out.append({**row, "hook": item["hook"], "body": render_citations(item["body"], data["brief"].get("sources") or []),
                    "issues": issues, "sources": data["brief"].get("sources") or []})
    return out
