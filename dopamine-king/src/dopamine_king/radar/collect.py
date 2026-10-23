"""Real web search results, collected through the logged-in Claude Code.

``claude -p`` is started with only the WebSearch tool enabled and told to run one search. The command streams its events;
the tool result in that stream is the real search result, so links are copied from it exactly as returned and the model's
own words are never used as data. A record is accepted only when the tool was really called with the requested query and
domain filter and the command reports at least one web search. The tool's summary is machine written text about the pages;
it is kept apart and always labelled as such. Long dashes are replaced by a hyphen, the only change made to any text.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from ..generate.providers import normalize_dashes

SYSTEM_PROMPT = ("You are a search relay. Call the WebSearch tool exactly once, with the query and the domain filter you are given, "
                 "character for character. Do not call any other tool. When the tool has returned, answer with the single word DONE.")
TOOL_NAME = "claude-code WebSearch"


class SearchError(RuntimeError):
    """A search that did not run as asked; nothing is recorded for it."""


def _clean(text: Any) -> str:
    return normalize_dashes(re.sub(r"[ \t]+", " ", str(text or "")).strip())


def _fold(text: str) -> str:
    """Comparable form of a query: spaces collapsed, lower case, one pair of surrounding quotation marks ignored (an exact-phrase search)."""
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text[1:-1].strip() if len(text) > 2 and text[0] in "\"'“„" and text[-1] in "\"'”“" else text


# -- reading the event stream --------------------------------------------------------------------------------------------
def _links_and_summary(result: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
    links: list[dict[str, str]] = []
    summary: list[str] = []
    for part in result.get("results") or []:
        if isinstance(part, str):
            summary.append(part.strip())
        elif isinstance(part, dict):
            for item in part.get("content") or []:
                if isinstance(item, dict) and isinstance(item.get("url"), str):
                    links.append({"title": str(item.get("title") or ""), "url": item["url"]})
    return links, "\n\n".join(s for s in summary if s)


def parse_events(stdout: str) -> dict[str, Any]:
    """The WebSearch calls with their results, and the usage reported at the end, from ``--output-format stream-json`` output."""
    calls: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    final: dict[str, Any] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        blocks = [b for b in (message.get("content") or []) if isinstance(b, dict)] if isinstance(message.get("content"), list) else []
        kind = event.get("type")
        if kind == "assistant":
            for block in blocks:
                if block.get("type") == "tool_use" and block.get("name") == "WebSearch" and block.get("id"):
                    calls[block["id"]] = {"input": block.get("input") or {}, "links": None, "summary": ""}
                    order.append(block["id"])
        elif kind == "user":
            ids = [b.get("tool_use_id") for b in blocks if b.get("type") == "tool_result"]
            result = event.get("tool_use_result")
            if ids and ids[0] in calls and isinstance(result, dict):
                calls[ids[0]]["links"], calls[ids[0]]["summary"] = _links_and_summary(result)
        elif kind == "result":
            final = event
    usage = final.get("modelUsage") if isinstance(final.get("modelUsage"), dict) else {}
    searches = sum(int(v.get("webSearchRequests") or 0) for v in usage.values() if isinstance(v, dict))
    if not searches and isinstance(final.get("usage"), dict):
        searches = int((final["usage"].get("server_tool_use") or {}).get("web_search_requests") or 0)
    model = next((k for k, v in usage.items() if isinstance(v, dict) and v.get("webSearchRequests")), next(iter(usage), ""))
    return {"calls": [calls[i] for i in order], "final": final, "web_searches": searches, "model": model,
            "cost_usd": final.get("total_cost_usd")}


# -- one search ----------------------------------------------------------------------------------------------------------
def build_prompt(query: str, allowed_domains: Sequence[str] = ()) -> str:
    text = f"Call WebSearch once with this exact query: {json.dumps(query, ensure_ascii=False)}"
    if allowed_domains:
        text += f" and this exact allowed_domains list: {json.dumps(list(allowed_domains))}"
    return text + ". Do not change anything. Then answer DONE."


def command(prompt: str, *, model: str = "haiku", executable: str | None = None) -> list[str]:
    exe = executable or os.environ.get("KING_CLAUDE_BIN") or "claude"
    return [exe, "-p", prompt, "--tools", "WebSearch", "--allowedTools", "WebSearch", "--output-format", "stream-json", "--verbose",
            "--no-session-persistence", "--strict-mcp-config", "--disable-slash-commands", "--max-budget-usd", "0.5",
            "--system-prompt", SYSTEM_PROMPT, "--model", model]


def search(query: str, allowed_domains: Sequence[str] = (), *, model: str = "haiku", executable: str | None = None, timeout: float = 240.0,
           runner: Callable[..., Any] | None = None, now: Callable[[], datetime] | None = None) -> dict[str, Any]:
    """Run one real web search and return what the tool returned; raise ``SearchError`` when it did not run exactly as asked."""
    run = runner or subprocess.run
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)                    # the subscription pays, never a stray API key
    cmd = command(build_prompt(query, allowed_domains), model=model, executable=executable)
    try:
        with tempfile.TemporaryDirectory() as workdir:
            proc = run(cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=workdir, stdin=subprocess.DEVNULL)
    except FileNotFoundError as err:
        raise SearchError(f"The command {cmd[0]!r} was not found. Install Claude Code and log in (run claude, then /login).") from err
    except subprocess.TimeoutExpired as err:
        raise SearchError(f"No answer within {timeout:.0f} seconds.") from err
    if proc.returncode != 0:
        raise SearchError(f"Claude Code failed (exit {proc.returncode}): {(proc.stderr or proc.stdout or '').strip()[-300:] or 'no message'}")
    parsed = parse_events(proc.stdout)
    final = parsed["final"]
    if not final:
        raise SearchError("The command ended without a result event.")
    if final.get("is_error"):
        raise SearchError(f"Claude Code reported an error: {str(final.get('result') or final.get('subtype') or 'unknown')[:300]}")
    if not parsed["calls"]:
        raise SearchError("The model did not call the WebSearch tool.")
    call = parsed["calls"][0]
    sent = call["input"]
    if _fold(str(sent.get("query") or "")) != _fold(query):
        raise SearchError(f"The tool was called with another query: {sent.get('query')!r}")
    wanted = {d.lower() for d in allowed_domains}
    if {str(d).lower() for d in (sent.get("allowed_domains") or [])} != wanted:
        raise SearchError(f"The tool was called with another domain filter: {sent.get('allowed_domains')!r}")
    if call["links"] is None:
        raise SearchError("The tool returned no result.")
    if parsed["web_searches"] < 1:
        raise SearchError("The command reports no web search request.")
    stamp = (now or (lambda: datetime.now(timezone.utc)))().strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "query": query, "query_sent": str(sent.get("query")), "allowed_domains": sorted(wanted), "mode": str(sent.get("mode") or ""),
        "retrieved_at": stamp, "tool": TOOL_NAME, "model": parsed["model"], "web_searches": parsed["web_searches"],
        "links": [{"rank": i + 1, "title": _clean(link["title"]), "url": link["url"].strip()} for i, link in enumerate(call["links"])],
        "summary": _clean(call["summary"]),
    }


# -- the plan and the snapshot ---------------------------------------------------------------------------------------------
def load_plan(path: str | Path) -> dict[str, Any]:
    plan = json.loads(Path(path).read_text("utf-8"))
    ids = [q["id"] for q in plan["queries"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate query ids in the plan")
    for q in plan["queries"]:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", q["id"]):
            raise ValueError(f"bad query id {q['id']!r}")
    return plan


def collect(plan: dict[str, Any], out_dir: str | Path, *, only: Sequence[str] | None = None, jobs: int = 4, model: str = "haiku",
            force: bool = False, search_fn: Callable[..., dict[str, Any]] = search, log: Callable[[str], None] = print,
            retries: int = 1) -> dict[str, Any]:
    """Run the plan's searches that are not stored yet and write one ``raw/<id>.json`` per accepted record."""
    out = Path(out_dir)
    raw = out / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    todo = [q for q in plan["queries"] if (not only or q["id"] in only) and (force or not (raw / f"{q['id']}.json").exists())]
    errors: dict[str, str] = {}

    def one(q: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None, str]:
        last = ""
        for _ in range(retries + 1):
            try:
                rec = search_fn(q["q"], q.get("domains", []), model=model)
                return q, rec, ""
            except SearchError as err:
                last = str(err)
        return q, None, last

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = [pool.submit(one, q) for q in todo]
        for done, future in enumerate(as_completed(futures), 1):
            q, rec, err = future.result()
            if rec is None:
                errors[q["id"]] = err
                log(f"[{done}/{len(todo)}] {q['id']}: FAILED {err}")
                continue
            rec.update({"id": q["id"], "group": q["group"], "persona": q.get("persona", ""), "purpose": _clean(q.get("purpose", ""))})
            (raw / f"{q['id']}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", "utf-8")
            log(f"[{done}/{len(todo)}] {q['id']}: {len(rec['links'])} links")
    write_manifest(out, plan)
    return {"requested": len(todo), "stored": len(todo) - len(errors), "errors": errors}


def load_records(snapshot: str | Path, plan: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """All stored records of a snapshot, in plan order when the plan is given."""
    records = [json.loads(p.read_text("utf-8")) for p in sorted((Path(snapshot) / "raw").glob("*.json"))]
    if plan:
        position = {q["id"]: i for i, q in enumerate(plan["queries"])}
        records.sort(key=lambda r: position.get(r["id"], len(position)))
    return records


def write_manifest(snapshot: str | Path, plan: dict[str, Any]) -> dict[str, Any]:
    records = load_records(snapshot, plan)
    stamps = sorted(r["retrieved_at"] for r in records)
    manifest = {
        "tool": TOOL_NAME, "plan": plan.get("name", ""), "records": len(records), "planned": len(plan["queries"]),
        "first_retrieved_at": stamps[0] if stamps else "", "last_retrieved_at": stamps[-1] if stamps else "",
        "models": sorted({r.get("model", "") for r in records}),
        "missing": [q["id"] for q in plan["queries"] if q["id"] not in {r["id"] for r in records}],
        "note": ("Links are copied from the search tool's result exactly as returned. The summary is machine written text about "
                 "the pages. Long dashes were replaced by a hyphen, nothing else was changed."),
    }
    (Path(snapshot) / "snapshot.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return manifest
