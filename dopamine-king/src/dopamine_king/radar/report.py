"""The radar report: one self-contained HTML page in plain Czech, built from a snapshot, the study ledger and the drafts.

No network, no external fonts or scripts, no tracking. Every number on the page comes from ``analyze``; every sentence that depends on
a number comes from ``compose``. Text from the web is escaped, links open in a new tab.
"""
from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path
from typing import Any

from ..generate.claims import load_profile
from ..generate.providers import normalize_dashes
from ..verticals import load_vertical
from . import analyze as A
from . import compose as C
from . import emotion
from .collect import load_plan, load_records
from .drafts import load_drafts

GROUPS_CS = {"brand": "Značka", "category": "Kategorie", "persona": "Cílové skupiny", "competitor": "Konkurenti", "own": "Váš web",
             "brandsite": "Weby značek", "study": "Studie"}
CLASS_CS = {"context": "vysvětlení", "wellness": "pohoda a výkon", "cosmetic": "vzhled", "medical": "zdravotní téma", "avoid": "zakázané téma"}
LABEL_CS = {"none": "bez ověřených studií", "limited": "omezené důkazy", "contested": "sporné důkazy", "moderate": "střední důkazy", "strong": "silné důkazy"}
TRAFFIC = {"context": ("ok", "Můžete vysvětlovat"), "wellness": ("warn", "Jen opatrně"), "cosmetic": ("warn", "Jen opatrně a se zdrojem"),
           "medical": ("stop", "Neříkejte"), "avoid": ("stop", "Neříkejte")}
DIRECTION_CS = {"supports": "podporuje", "mixed": "smíšené nálezy", "contradicts": "odporuje", "context": "souvislost"}
CODE_CS = {"CLAIM_MEDICAL": "zdravotní tvrzení", "CLAIM_AVOID": "zakázané téma", "STATUS_CLAIM": "tvrzení o postavení", "SAFETY_ABSOLUTE": "absolutní tvrzení o bezpečnosti",
           "OUTCOME_PROMISE": "slib výsledku", "DISEASE_MENTION": "zmínka o nemoci", "MEDICATION_ADVICE": "rada o lécích"}
RISK_CS = {"high": ("warn", "vyšší riziko tvrzení"), "medium": ("none", "střední riziko"), "low": ("ok", "nižší riziko")}
MONTHS_CS = ["ledna", "února", "března", "dubna", "května", "června", "července", "srpna", "září", "října", "listopadu", "prosince"]


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def date_cs(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{d.day}. {d.month}. {d.year}"


def tool_label(tool: str) -> str:
    """The tool as the reader knows it. The snapshot also stores the exact tool string, which is not meant for readers."""
    return "Claude Code" if tool.lower().startswith("claude-code") else tool


def link(url: str, label: str) -> str:
    return f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(label)}</a>'


# -- data ------------------------------------------------------------------------------------------------------------------
def science(vertical: Any, snapshot_date: str) -> dict[str, Any]:
    own_ids = [s["id"] for s in json.loads((vertical.path / "ledger.json").read_text("utf-8"))["studies"]]
    by_id = {s.id: s for s in vertical.ledger().studies}
    studies = [by_id[i] for i in own_ids if i in by_id]
    marker = f"web search on {snapshot_date}"
    now = [s for s in studies if s.verified and marker in s.verification_note]
    pending = [s for s in studies if not s.verified]
    return {"total": len(studies), "verified": sum(s.verified for s in studies), "pending": len(pending), "verified_now": len(now),
            "new": [{"title": s.title, "venue": s.venue or "", "year": s.year or "", "url": s.url or (f"https://doi.org/{s.doi}" if s.doi else ""),
                     "design": s.design} for s in now],
            "unverified": [{"title": s.title, "note": s.verification_note} for s in pending]}


def report_data(snapshot: str | Path, drafts: str | Path, plan_path: str | Path) -> dict[str, Any]:
    root = Path(plan_path).resolve().parent
    plan = load_plan(plan_path)
    records = load_records(snapshot, plan)
    direct = A.load_direct(snapshot)
    vertical = load_vertical("pbm")
    cfg = A.load_config(root, json.loads((vertical.path / "brands.json").read_text("utf-8")))
    profile = load_profile("pbm", "wellness")
    cmap = vertical.claim_map(vertical.ledger())
    manifest = json.loads((Path(snapshot) / "snapshot.json").read_text("utf-8"))
    stamp = manifest["last_retrieved_at"][:10]
    own = A.own_pages(records, plan["brand"], cfg["themes"])
    data: dict[str, Any] = {
        "brand": plan["brand"], "plan_name": plan.get("name", ""),
        "meta": {"date": stamp, "date_cs": date_cs(stamp), "searches": len(records), "direct": len(direct),
                 "links": sum(len(r["links"]) for r in records), "hosts": len({A.host_of(l["url"]) for r in records for l in r["links"]}),
                 "tool": tool_label(manifest["tool"]), "first": manifest["first_retrieved_at"], "last": manifest["last_retrieved_at"],
                 "missing": manifest["missing"]},
        "visibility": A.visibility(records, plan["brand"]),
        "landscape": A.landscape(records, cfg["domains"]),
        "identity": A.identity(records, plan["brand"], cfg["domains"], direct),
        "brandsites": A.brandsites(records, cfg["themes"], cfg["domains"]),
        "own": own,
        "own_titles": A.outcome_titles(own["pages"], profile, cmap, cfg["outcome"]),
        "claims_audit": A.claims_audit(records, profile, cfg["domains"], own_domains=plan["brand"]["own_domains"]),
        "science": science(vertical, stamp),
        "claim_map": cmap,
        "validation": A.validation(records, direct),
        "queries": [{"id": r["id"], "group": r["group"], "query": r["query"], "purpose": r.get("purpose", ""), "retrieved_at": r["retrieved_at"],
                     "domains": r.get("allowed_domains", []), "links": [{"rank": l["rank"], "title": A.display(l)["label"], "url": l["url"]} for l in r["links"]]}
                    for r in records],
        "direct": [{"id": x["id"], "query": x["query"], "domains": x.get("allowed_domains", []), "retrieved_on": x["retrieved_on"],
                    "links": [{"rank": l["rank"], "title": A.display(l)["label"], "url": l["url"]} for l in x["links"]]} for x in direct],
        "drafts": load_drafts(drafts),
        "emotion": emotion.section_data(emotion.load(root / "claims_emotional.json"), vertical, vertical.ledger(), vertical.personas()),
    }
    data["findings"] = C.findings(data)
    data["actions"] = C.actions(data)
    data["open_items"] = C.open_items(data)
    return data


# -- pieces ------------------------------------------------------------------------------------------------------------------
def evidence_chips(ids: list[str], known: set[str]) -> str:
    return "".join(f'<a class="chip" href="#q-{esc(i)}">{esc(i)}</a>' for i in ids if i in known)


def render_findings(d: dict[str, Any]) -> str:
    known = {q["id"] for q in d["queries"]} | {x["id"] for x in d["identity"]["quotes"]}
    cards = []
    for f in d["findings"]:
        cards.append(f'''<article class="finding" id="f-{esc(f["id"])}">
  <div class="big">{esc(f["number"])}</div>
  <h3>{esc(f["title"])}</h3>
  <p>{esc(f["text"])}</p>
  <p class="caveat"><b>Pozor:</b> {esc(f["caveat"])}</p>
  <p class="src">Podklad: {evidence_chips(f["evidence"], known) or "souhrn všech hledání"}</p>
</article>''')
    return '<div class="grid">' + "".join(cards) + "</div>"


def render_actions(d: dict[str, Any]) -> str:
    items = []
    for a in d["actions"]:
        steps = "".join(f"<li>{esc(s)}</li>" for s in a["steps"])
        items.append(f'''<li class="todo" data-id="{esc(a["id"])}">
  <label class="todo-head"><input type="checkbox" id="chk-{esc(a["id"])}"><span class="todo-title">{esc(a["title"])}</span></label>
  <p class="why">{esc(a["why"])}</p>
  <details><summary>Jak na to</summary><ol>{steps}</ol></details>
</li>''')
    return f'<ol class="todos">{"".join(items)}</ol><p class="progress" aria-live="polite"><span id="progress-text">Splněno 0 z {len(d["actions"])}</span><span class="track"><span id="progress-bar"></span></span></p>'


def render_visibility(d: dict[str, Any]) -> str:
    rows = []
    for r in d["visibility"]["rows"]:
        own = f'<span class="pill ok">{r["own_rank"]}. místo</span>' if r["own_rank"] else '<span class="pill none">nenalezen</span>'
        top = r["top"]
        first = f'{link(top["url"], top["title"][:70])} <span class="host">{esc(top["host"])}</span>' if top else ""
        rows.append(f'<tr data-group="{esc(r["group"])}"><td data-label="Hledaný výraz"><a href="#q-{esc(r["id"])}">{esc(r["query"])}</a></td>'
                    f'<td data-label="Váš web">{own}</td><td class="wrap" data-label="První výsledek">{first}</td></tr>')
    chips = '<button class="fchip on" data-filter="all" type="button">Vše</button>' + "".join(
        f'<button class="fchip" data-filter="{g}" type="button">{GROUPS_CS[g]}</button>' for g in ("brand", "category", "persona", "competitor"))
    v = d["visibility"]
    return (f'<p class="lead">Váš web se objevil v <b>{v["all"]["own"]} z {v["all"]["queries"]}</b> hledání. Sloupec vpravo ukazuje, kdo je ve výsledcích první.</p>'
            f'<div class="filters" role="group" aria-label="Filtr hledání">{chips}</div>'
            f'<div class="scroll"><table class="tbl stack" id="vis"><thead><tr><th>Hledaný výraz</th><th>Váš web</th><th>První výsledek</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def render_landscape(d: dict[str, Any]) -> str:
    land = d["landscape"]
    n = d["visibility"]["market"]["queries"]
    rows = []
    for x in land["domains"][:22]:
        width = round(100 * x["queries"] / max(1, n))
        label = land["types"].get(x["type"], x["type"])
        rows.append(f'<li><div class="bar-head"><b>{esc(x["name"])}</b> <span class="tag t-{esc(x["type"])}">{esc(label)}</span><span class="val">{x["queries"]} z {n}</span></div>'
                    f'<div class="track"><span style="width:{width}%"></span></div>'
                    + (f'<div class="note">{esc(x["note"])}</div>' if x["note"] else "") + "</li>")
    return (f'<p class="lead">V {n} českých hledáních (kategorie, cílové skupiny, konkurenti) vrátil nástroj {land["links"]} odkazů z {land["hosts"]} webů. '
            f'Níže jsou weby zařazené ručně; {land["noise_links"]} odkazů nesouviselo s oborem a {land["unclassified_links"]} zůstalo nezařazených.</p>'
            f'<ul class="bars">{"".join(rows)}</ul>')


def render_identity(d: dict[str, Any]) -> str:
    ident = d["identity"]
    rows = []
    for r in ident["rows"]:
        share = round(100 * r["lookalike"] / max(1, r["links"]))
        rows.append(f'<li><div class="bar-head"><a href="#q-{esc(r["id"])}">{esc(r["query"])}</a><span class="val">{r["lookalike"]} z {r["links"]} na Mito Red Light</span></div>'
                    f'<div class="track warm"><span style="width:{share}%"></span></div></li>')
    about = "".join(f'<li>{link(a["url"], a["title"][:80])} <span class="host">{esc(a["host"])}</span></li>' for a in ident["about"])
    def lang(text: str) -> str:
        return "" if any(ch in "ěščřžýáíéúůďťň" for ch in text.lower()) else " (anglicky)"
    quotes = "".join(f'<blockquote><p>{esc(q["text"])}</p><footer>Strojové shrnutí vyhledávače{lang(q["text"])}, hledání <a href="#q-{esc(q["id"])}">{esc(q["id"])}</a>. Nejde o text stránky.</footer></blockquote>'
                     for q in ident["quotes"])
    return (f'<h3>Kolik odkazů vede na jinou značku</h3><ul class="bars">{"".join(rows)}</ul>'
            f'<h3>Kde o vás píše někdo jiný</h3><ul class="plain">{about}</ul>'
            f'<h3>Co o vztahu k Mito Red Light tvrdí strojová shrnutí</h3>{quotes or "<p>Žádná shrnutí o vztahu obou značek nebyla ve výsledcích.</p>"}')


def render_themes(d: dict[str, Any]) -> str:
    b = d["brandsites"]
    own_themes = d["own"]["themes"]
    rows = []
    for t in b["themes"]:
        mk, md = t["maker"], t["media"]
        mine = own_themes.get(t["id"], 0)
        example = t["examples"][0] if t["examples"] else None
        ex = f'{link(example["url"], example["title"][:60])} <span class="host">{esc(example["site"])}</span>' if example else ""
        rows.append(f'<tr><td>{esc(t["name"])}</td><td class="num">{mk["pages"]}</td><td class="num">{md["pages"]}</td><td class="num mine">{mine}</td><td class="wrap">{ex}</td></tr>')
    failed = [s["name"] for s in b["sites"] if not s["pages"]]
    return (f'<p class="lead">Tabulka vychází z {b["pages"]} stránek z {b["sites_with_pages"]} webů: {b["makers"]} výrobců a {b["media"]} recenzních webů. '
            f'Ukazuje, kolik stránek patří k jednotlivým tématům.'
            + (f' U těchto webů vyhledávač nevrátil žádnou stránku: {esc(", ".join(failed))}.' if failed else "") + '</p>'
            f'<div class="scroll"><table class="tbl"><thead><tr><th>Téma</th><th>Výrobci</th><th>Recenzní weby</th><th>Váš web</th><th>Příklad</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
            f'<p class="caveat">Témata se přiřazují podle slov v názvu a adrese stránky. Váš web: {len(d["own"]["pages"])} stránek, které vyhledávač zná.</p>')


def render_claim_map(d: dict[str, Any]) -> str:
    groups = {"ok": [], "warn": [], "stop": []}
    for row in d["claim_map"]:
        tone, label = TRAFFIC[row["class"]]
        safe = (row["safe_cs"] or [""])[0]
        avoid = (row["avoid_cs"] or [""])[0]
        groups[tone].append(f'''<details class="topic {tone}"><summary><span class="tname">{esc(row["name_cs"])}</span>
  <span class="pill {tone}">{esc(label)}</span> <span class="pill lab">{esc(LABEL_CS[row["label"]])}, {C.count(row["n_studies"], "studie", "studie", "studií")}</span></summary>
  <div class="tbody"><p><b>Smíte říct:</b> {esc(safe)}</p><p><b>Neříkejte:</b> {esc(avoid)}</p><p class="muted">{esc(row["headline_cs"])}</p></div></details>''')
    order = [("ok", "Můžete vysvětlovat"), ("warn", "Jen opatrně a se zdrojem"), ("stop", "Neříkejte")]
    return "".join(f'<h3>{title} <span class="muted">({len(groups[t])})</span></h3>{"".join(groups[t])}' for t, title in order)


def render_own_titles(d: dict[str, Any]) -> str:
    rows = []
    for t in d["own_titles"]:
        tone, label = TRAFFIC[t["class"]]
        rows.append(f'<tr><td data-label="Stránka">{link(t["url"], t["title"])}</td><td data-label="Téma">{esc(t["topic"])}</td>'
                    f'<td data-label="Pravidlo"><span class="pill {tone}">{esc(label)}</span><br><span class="muted">{esc(LABEL_CS.get(t["label"], ""))}</span></td>'
                    f'<td class="wrap" data-label="Bezpečnější věta">{esc(t["safe"])}</td></tr>')
    if not rows:
        return "<p>Žádný z názvů stránek vašeho webu neslibuje výsledek.</p>"
    return (f'<p class="lead">{len(d["own_titles"])} z {len(d["own"]["pages"])} názvů vašich stránek obsahuje téma z mapy tvrzení a slovo, které slibuje výsledek.</p>'
            '<div class="scroll"><table class="tbl stack"><thead><tr><th>Stránka</th><th>Téma</th><th>Pravidlo</th><th>Bezpečnější věta</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def render_market_claims(d: dict[str, Any]) -> str:
    a = d["claims_audit"]
    rows = "".join(f'<tr><td data-label="Kdo">{esc(e["name"])}</td><td data-label="Název stránky">{link(e["url"], e["title"][:90])}</td><td data-label="Pravidlo">{esc(e["rule"])}</td>'
                   f'<td data-label="Část názvu"><mark>{esc(e["fragment"])}</mark></td></tr>' for e in a["examples"])
    return (f'<p class="lead">Z {a["scanned"]} názvů stránek prodejců, výrobců a médií v oboru jich {a["flagged"]} obsahuje tvrzení, které váš profil blokuje. '
            'Otázky, stránky o jiném tématu a stránky bez smysluplného názvu se nekontrolovaly.</p>'
            f'<div class="scroll"><table class="tbl stack"><thead><tr><th>Kdo</th><th>Název stránky</th><th>Pravidlo</th><th>Část názvu</th></tr></thead><tbody>{rows}</tbody></table></div>')


def render_drafts(d: dict[str, Any]) -> str:
    cards = []
    for x in d["drafts"]:
        shown = [i for i in x["issues"] if i["code"] != "AI_DISCLOSURE_REMINDER"]
        n_err = sum(i["severity"] == "error" for i in shown)
        n_warn = sum(i["severity"] == "warn" for i in shown)
        tone = "stop" if n_err else "warn" if n_warn else "ok"
        verdict = "Zablokováno" if n_err else f"Ke kontrole, varování: {n_warn}" if n_warn else "Bez varování"
        issues = "".join(f'<li><span class="pill {"stop" if i["severity"] == "error" else "warn" if i["severity"] == "warn" else "none"}">{esc(i["severity"])}</span> <b>{esc(i["code"])}</b> {esc(i["message"])}</li>'
                         for i in shown)
        kind = "Stránka" if x["kind"] == "page" else "Příspěvek"
        approval = f'<p class="approve"><b>Ke schválení:</b> {esc(x["needs_approval"])}</p>' if x["needs_approval"] else ""
        sources = ""
        if x["sources"]:
            cited = [s for i, s in enumerate(x["sources"], 1) if f"[{i}]" in x["body"]]
            sources = ("<details><summary>Zdroje v textu</summary><ol>" + "".join(
                f'<li>{link(s.get("url", ""), s.get("title", ""))}</li>' for s in x["sources"]) + "</ol></details>") if cited else ""
        cards.append(f'''<article class="draft" id="d-{esc(x["id"])}">
  <header><span class="kind">{kind}</span><h3>{esc(x["title"])}</h3><span class="pill {tone}">{esc(verdict)}</span></header>
  {approval}
  <details><summary>Otevřít text</summary>
    <pre class="text" id="t-{esc(x["id"])}">{esc(x["body"])}</pre>
    <button class="copy" type="button" data-target="t-{esc(x["id"])}">Kopírovat text</button>
  </details>
  <details><summary>Poznámky kontroly tvrzení ({len(shown)})</summary><ul class="issues">{issues}</ul></details>
  {sources}
</article>''')
    return "".join(cards)


def render_science(d: dict[str, Any]) -> str:
    s = d["science"]
    rows = "".join(f'<tr><td>{link(x["url"], x["title"][:96]) if x["url"] else esc(x["title"][:96])}</td><td>{esc(x["venue"])}</td><td class="num">{esc(x["year"])}</td></tr>' for x in s["new"])
    pend = "".join(f'<li><b>{esc(x["title"])}</b><br><span class="muted">{esc(x["note"])}</span></li>' for x in s["unverified"])
    return (f'<p class="lead">Registr má {s["total"]} studií, z toho {s["verified"]} ověřených. K {d["meta"]["date_cs"]} bylo ověřeno {s["verified_now"]} nových. '
            'Ověřená studie znamená, že se její název, časopis a rok objevily ve veřejném zdroji (PubMed, PubMed Central, vydavatel). Neznamená to, že byl přečten celý text.</p>'
            f'<div class="scroll"><table class="tbl"><thead><tr><th>Nově ověřeno</th><th>Časopis</th><th>Rok</th></tr></thead><tbody>{rows}</tbody></table></div>'
            f'<h3>Zůstává neověřeno</h3><ul class="plain">{pend}</ul>')


def render_open(d: dict[str, Any]) -> str:
    return '<ul class="open">' + "".join(
        f'<li><b>{esc(x["what"])}</b><br>{esc(x["why"])}<br><span class="need">Potřeba: {esc(x["need"])}</span></li>' for x in d["open_items"]) + "</ul>"


def render_method(d: dict[str, Any]) -> str:
    m = d["meta"]
    val = "".join(f'<tr><td>{esc(v["query"])}</td><td class="num">{v["shared"]} z {v["direct_links"]}</td><td>{"ano" if v["same_order"] else "ne"}</td></tr>' for v in d["validation"])
    groups: dict[str, list[dict[str, Any]]] = {}
    for q in d["queries"]:
        groups.setdefault(q["group"], []).append(q)
    appendix = []
    for g, qs in groups.items():
        items = []
        for q in qs:
            rows = "".join(f'<li><span class="rk">{l["rank"]}</span> {link(l["url"], l["title"][:90])} <span class="host">{esc(A.host_of(l["url"]))}</span></li>' for l in q["links"])
            dom = f' <span class="host">jen {esc(", ".join(q["domains"]))}</span>' if q["domains"] else ""
            items.append(f'<details id="q-{esc(q["id"])}"><summary><b>{esc(q["id"])}</b> {esc(q["query"])}{dom}</summary><p class="muted">{esc(q["purpose"])} Staženo {esc(q["retrieved_at"])}.</p><ol class="links">{rows}</ol></details>')
        appendix.append(f'<h4>{esc(GROUPS_CS.get(g, g))} ({len(qs)})</h4>{"".join(items)}')
    direct_items = "".join(
        f'<details id="q-{esc(x["id"])}"><summary><b>{esc(x["id"])}</b> {esc(x["query"])}'
        + (f' <span class="host">jen {esc(", ".join(x["domains"]))}</span>' if x["domains"] else "")
        + f'</summary><p class="muted">Hledání provedl Claude přímo nástrojem pro vyhledávání dne {esc(x["retrieved_on"])}.</p><ol class="links">'
        + "".join(f'<li><span class="rk">{l["rank"]}</span> {link(l["url"], l["title"][:90])} <span class="host">{esc(A.host_of(l["url"]))}</span></li>' for l in x["links"])
        + "</ol></details>" for x in d["direct"])
    appendix.append(f'<h4>Kontrola přímým hledáním ({len(d["direct"])})</h4>{direct_items}')
    return f'''<p>Data pocházejí z <b>{m["searches"]} skutečných hledání na webu</b> ze dne {esc(m["date_cs"])}. Každé hledání spustil nástroj Claude Code s jediným povoleným nástrojem, vyhledáváním na webu.
Uložené odkazy jsou přesně to, co nástroj vrátil. Hledání se uloží jen tehdy, když nástroj opravdu proběhl s požadovaným dotazem. Nic se nedopisuje, nezaokrouhluje ani nesimuluje.</p>
<ul class="plain">
<li>Vyhledávač hledá z USA a není to Google.cz ani Seznam. Pořadí a výběr se od českých výsledků mohou lišit.</li>
<li>Jde o jeden snímek. Při dalším hledání se výsledky mírně změní.</li>
<li>Nástroj ukazuje názvy a adresy stránek, ne jejich obsah. Souhrny, které přidává, píše stroj.</li>
<li>Zařazení webů a témat jsou úsudky podle názvů, adres a ručně sestaveného seznamu.</li>
<li>Dlouhé pomlčky v názvech byly nahrazeny spojovníkem, jiná úprava se nedělala.</li>
</ul>
<h4>Kontrola proti přímému hledání</h4>
<p>Pět hledání bylo zopakováno přímo nástrojem pro vyhledávání a odkazy byly porovnány s uloženými.</p>
<div class="scroll"><table class="tbl"><thead><tr><th>Hledání</th><th>Shodné odkazy</th><th>Stejné pořadí</th></tr></thead><tbody>{val}</tbody></table></div>
<h4>Všechna hledání</h4>
{"".join(appendix)}'''


def studies_cs(n: int) -> str:
    return C.count(n, "ověřená studie", "ověřené studie", "ověřených studií")


def copy_button(target: str) -> str:
    return f'<button class="copy" type="button" data-target="{esc(target)}">Kopírovat text</button>'


def use_name(uses: dict[str, str], key: str) -> str:
    return uses[key].split(":")[0]


def verdict_pill(c: dict[str, Any]) -> str:
    """Nothing for a sentence the shield passed; the findings for one it did not."""
    v = c["verdict"]
    if v["errors"]:
        return f'<span class="pill stop">{esc(", ".join(CODE_CS.get(x, x) for x in v["errors"]))}</span>'
    if v["warnings"]:
        return f'<span class="pill warn">{esc(", ".join(CODE_CS.get(x, x) for x in v["warnings"]))}</span>'
    return ""


def needs_note(c: dict[str, Any]) -> str:
    return f'<p class="approve"><b>Potvrdit:</b> {esc(c["needs"])}</p>' if c.get("needs") else ""


def facts_note(c: dict[str, Any]) -> str:
    return f'<p class="muted"><b>Opírá se o:</b> {esc(" ".join(c["facts"]))}</p>' if c.get("facts") else ""


def claim_row(c: dict[str, Any], uses: dict[str, str], names: dict[str, str] | None = None) -> str:
    cid = c["id"]
    tags = f'<span class="tag">{esc(use_name(uses, c["use"]))}</span>'
    if names:
        tags += f'<span class="tag">{esc(names[c["lever"]])}</span>'
    if c.get("where_cs"):
        tags += f'<span class="tag">{esc(c["where_cs"])}</span>'
    if c.get("concept"):
        tags += '<span class="pill none">Koncept</span>'
    return (f'<li class="claim" id="c-{esc(cid)}"><p class="ctext" id="t-c-{esc(cid)}">{esc(c["text"])}</p>'
            f'<div class="cmeta">{tags}{verdict_pill(c)}{copy_button("t-c-" + cid)}</div>{needs_note(c)}{facts_note(c)}</li>')


def study_item(s: dict[str, Any]) -> str:
    title = link(s["url"], s["title"][:110]) if s["url"] else esc(s["title"][:110])
    return (f'<li>{title} <span class="host">{esc(s["year"])}, {esc(DIRECTION_CS.get(s["direction"], s["direction"]))}</span>'
            f'<br><span class="muted">{esc(s["note"])}</span></li>')


def evidence_list(evidence: list[dict[str, Any]]) -> str:
    blocks = []
    for e in evidence:
        studies = "".join(study_item(s) for s in e["studies"])
        ethics = f'<p class="caveat"><b>Pozor:</b> {esc(e["ethics"])}</p>' if e["ethics"] else ""
        blocks.append(f'<div class="evi"><p><b>{esc(e["name"])}</b> <span class="pill lab">{esc(LABEL_CS[e["label"]])}, {studies_cs(e["n_verified"])}</span></p>'
                      f'<p class="muted">{esc(e["headline"])}</p>' + (f'<ul class="plain">{studies}</ul>' if studies else "") + ethics + "</div>")
    return "".join(blocks)


def render_dopamine(e: dict[str, Any]) -> str:
    d = e["dopamine"]
    studies = "".join(study_item(s) for s in d["studies"])
    return f"""<div class="callout">
  <h3>Proč tu není slovo dopamin</h3>
  <p>Dopamin je lákavé téma, ale do textů pro zákazníky nepatří. Věta typu „zvyšuje dopamin“ tvrdí účinek přístroje na tělo, a to je zdravotní tvrzení. Kontrola tvrzení ji blokuje stejně jako „vyléčí“.</p>
  <p>{esc(d["summary"])} Claimy proto stojí na tom, co za dopaminem v běžném životě je: na těšení, rituálu a překvapení.</p>
  <p class="caveat"><b>Pozor:</b> {esc(d["ethics"])}</p>
  <details><summary>Studie k tématu ({studies_cs(d["n_verified"])})</summary><ul class="plain">{studies}</ul></details>
</div>"""


def render_picks(e: dict[str, Any]) -> str:
    cards = []
    for c in e["picks"]:
        cid = c["id"]
        kind = f'{use_name(e["uses"], c["use"])} · {e["lever_names"][c["lever"]]}'
        cards.append(f"""<li class="pick"><span class="kind">{esc(kind)}</span>
  <p class="big-claim" id="t-p-{esc(cid)}">{esc(c["text"])}</p>
  <p class="pwhy">{esc(c["why_cs"])}</p>{needs_note(c)}{facts_note(c)}
  <div class="cmeta">{verdict_pill(c)}{copy_button("t-p-" + cid)}</div></li>""")
    return f'<ul class="picks">{"".join(cards)}</ul>'


def render_levers(e: dict[str, Any]) -> str:
    out = []
    for lv in e["levers"]:
        rows = "".join(claim_row(c, e["uses"]) for c in lv["claims"])
        out.append(f"""<details class="topic lever" id="lever-{esc(lv["id"])}"><summary><span class="tname">{esc(lv["name_cs"])}</span>
  <span class="pill lab">{esc(LABEL_CS[lv["label"]])}, {studies_cs(lv["n_verified"])}</span> <span class="muted">{C.count(len(lv["claims"]), "věta", "věty", "vět")}</span></summary>
  <div class="tbody"><p>{esc(lv["what_cs"])}</p><p class="caveat"><b>Pozor:</b> {esc(lv["watch_cs"])}</p>
  <details><summary>Důkazy za touto pákou</summary>{evidence_list(lv["evidence"])}</details>
  <ul class="claims">{rows}</ul></div></details>""")
    return "".join(out)


def render_personas(e: dict[str, Any]) -> str:
    out = []
    for p in e["personas"]:
        tone, label = RISK_CS.get(p["risk"], ("none", ""))
        pill = f'<span class="pill {tone}">{esc(label)}</span>' if label else ""
        rows = "".join(claim_row(c, e["uses"], e["lever_names"]) for c in p["claims"])
        out.append(f'<details class="topic"><summary><span class="tname">{esc(p["name"])}</span> {pill}</summary><div class="tbody"><ul class="claims">{rows}</ul></div></details>')
    return "".join(out)


def render_claim_list(claims: list[dict[str, Any]], e: dict[str, Any]) -> str:
    return '<ul class="claims">' + "".join(claim_row(c, e["uses"], e["lever_names"]) for c in claims) + "</ul>"


def render_story(e: dict[str, Any]) -> str:
    versions = "".join(
        f'<details><summary>{esc(s["name_cs"])}</summary><pre class="text" id="t-{esc(s["id"])}">{esc(s["text"])}</pre>{copy_button("t-" + s["id"])}'
        f'<p class="muted"><b>Opírá se o:</b> {esc(" ".join(s["facts"]))}</p></details>' for s in e["story"])
    names = "".join(
        f'<li><b>{esc(n["name"])}</b>: {esc(n["meaning_cs"])}' + (f'<br><span class="need">Potvrdit: {esc(n["needs"])}</span>' if n.get("needs") else "") + "</li>" for n in e["naming"])
    return f'{versions}<h4>Jména pro rituál a funkce</h4><ul class="plain">{names}</ul>'


def render_forbidden(e: dict[str, Any]) -> str:
    rows = []
    for r in e["forbidden"]:
        found = " ".join(f'<span class="pill stop">{esc(CODE_CS.get(x, x))}</span>' for x in r["found"]) or '<span class="pill none">kontrola nezachytila</span>'
        rows.append(f'<tr><td data-label="Neříkejte"><mark>{esc(r["text"])}</mark></td><td class="wrap" data-label="Proč">{esc(r["why_cs"])}</td>'
                    f'<td data-label="Kontrola">{found}</td><td class="wrap" data-label="Místo toho">{esc(r["swap"])}</td></tr>')
    return ('<div class="scroll"><table class="tbl stack"><thead><tr><th>Neříkejte</th><th>Proč</th><th>Kontrola</th><th>Místo toho</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def render_guardrails(e: dict[str, Any]) -> str:
    items = []
    for g in e["guardrails"]:
        ev = "".join(f'<br><span class="muted"><b>{esc(x["name"])}:</b> {esc(LABEL_CS[x["label"]])}. {esc(x["ethics"])}</span>' for x in g["evidence"])
        items.append(f'<li><b>{esc(g["title_cs"])}</b><br>{esc(g["text_cs"])}{ev}</li>')
    return f'<ul class="open">{"".join(items)}</ul>'


def render_tests(e: dict[str, Any]) -> str:
    items = "".join(f'<li><b>{esc(t["hypothesis_cs"])}</b><br>A: „{esc(t["a_text"])}“<br>B: „{esc(t["b_text"])}“</li>' for t in e["tests"])
    return ('<p class="lead">Jedna věta ještě není vítěz. Pošlete obě verze stejně velké skupině lidí ve stejných dnech, měňte vždy jen jednu věc a porovnávejte kliknutí a odpovědi, ne dojem.</p>'
            f'<ul class="open">{items}</ul>')


def render_needs(e: dict[str, Any]) -> str:
    def quoted(x: str) -> str:
        return x if x.startswith("Název") else f"„{x}“"
    items = "".join(f'<li><b>{esc(n["need"])}</b><br><span class="muted">Týká se: {esc(", ".join(quoted(x) for x in n["texts"]))}</span></li>' for n in e["needs"])
    return f'<ul class="open">{items}</ul>'


def render_claims(d: dict[str, Any]) -> str:
    e = d["emotion"]
    t = e["totals"]
    verdict = ("Každá věta prošla kontrolou tvrzení bez chyby i varování." if not (t["errors"] or t["warnings"]) else
               f'Kontrola našla {C.count(t["errors"], "chybu", "chyby", "chyb")} a {C.count(t["warnings"], "varování", "varování", "varování")}, dotčené věty jsou označené.')
    return (f'<p class="lead">{C.count(t["claims"], "hotová věta", "hotové věty", "hotových vět")} pro slogany, nadpisy, příspěvky a texty v aplikaci. Stojí na {len(e["levers"])} pákách s oporou ve studiích '
            'a popisují okamžik, volbu nebo příběh značky. Žádná netvrdí účinek na tělo, náladu ani hormony.</p>'
            f'<p class="muted">{verdict} Kontrola hlídá slova, ne smysl, proto každou větu před zveřejněním přečte člověk. Síla důkazů platí pro obecnou páku (například těšení), ne pro konkrétní větu ani pro produkt. '
            'Štítek Koncept znamená nápad, který zatím nic netvrdí o přístroji (kampaň, předmět e-mailu, upozornění v aplikaci). Před použitím rozhodněte, zda z něj uděláte skutečnost.</p>'
            f'{render_dopamine(e)}'
            f'<h3>Deset vět, od kterých začít</h3><p class="muted">Pořadí neurčuje síla věty, tu nikdo nezná předem. Každá využívá páku s oporou ve studiích a nic neslibuje. Skutečnou sílu ukáže test.</p>{render_picks(e)}'
            f'<h3>Podle páky</h3>{render_levers(e)}'
            f'<h3>Podle cílové skupiny</h3>{render_personas(e)}'
            f'<h3>Slogany ({len(e["taglines"])})</h3>{render_claim_list(e["taglines"], e)}'
            f'<h3>Mikrotexty pro aplikaci, e-maily a balení</h3><details><summary>Otevřít {C.count(len(e["microcopy"]), "text", "texty", "textů")}</summary>{render_claim_list(e["microcopy"], e)}</details>'
            f'<h3>Příběh značky</h3>{render_story(e)}'
            f'<h3>Co říkat místo čeho</h3>{render_forbidden(e)}'
            f'<h3>Pravidla hry</h3>{render_guardrails(e)}'
            f'<h3>Co otestovat</h3>{render_tests(e)}'
            f'<h3>Než něco zveřejníte</h3><p class="muted">Co musí značka potvrdit, aby věty platily.</p>{render_needs(e)}')


# -- page ------------------------------------------------------------------------------------------------------------------------
CSS = """
:root {
  --bg: #f6f3f2; --panel: #ffffff; --fg: #1f191a; --muted: #6a5d60; --line: #e2d9da; --accent: #a8121a; --accent-ink: #ffffff; --accent-soft: #fbe8e9;
  --ok: #1a7447; --ok-soft: #e3f3ea; --warn: #8f5600; --warn-soft: #fbefd5; --stop: #a8121a; --stop-soft: #fbe3e5; --none-soft: #ece6e7;
  --head-a: #6d0d14; --head-b: #a8121a; --shadow: 0 1px 2px rgba(31,25,26,.08);
  --font: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; --mono: ui-monospace, "SF Mono", Consolas, "Liberation Mono", monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #161112; --panel: #211a1b; --fg: #f1e9ea; --muted: #b3a5a8; --line: #3a2e30; --accent: #ff7b6f; --accent-ink: #1a0b0c; --accent-soft: #3a1c1e;
  --ok: #6fd39b; --ok-soft: #173326; --warn: #f0b54e; --warn-soft: #3a2b10; --stop: #ff8a85; --stop-soft: #3d1b1e; --none-soft: #2c2325;
  --head-a: #3a0a0f; --head-b: #6d0d14; --shadow: none; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #161112; --panel: #211a1b; --fg: #f1e9ea; --muted: #b3a5a8; --line: #3a2e30; --accent: #ff7b6f; --accent-ink: #1a0b0c; --accent-soft: #3a1c1e;
  --ok: #6fd39b; --ok-soft: #173326; --warn: #f0b54e; --warn-soft: #3a2b10; --stop: #ff8a85; --stop-soft: #3d1b1e; --none-soft: #2c2325;
  --head-a: #3a0a0f; --head-b: #6d0d14; --shadow: none; color-scheme: dark; }
* { box-sizing: border-box; }
html { scroll-behavior: smooth; scroll-padding-top: 64px; }
body { background: var(--bg); color: var(--fg); font-family: var(--font); font-size: 16px; line-height: 1.55; margin: 0;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 0 48px; }
body::before { content: ""; position: fixed; inset: 0 0 auto; height: env(safe-area-inset-top, 0px); background: var(--head-a); z-index: 30; }
.wrap-page { max-width: 900px; margin: 0 auto; }
header.top { background: linear-gradient(135deg, var(--head-a), var(--head-b)); color: #fff; margin-inline: calc(-1 * max(16px, env(safe-area-inset-left, 0px))); padding: 28px max(16px, env(safe-area-inset-left, 0px)) 24px; }
header.top .in { max-width: 900px; margin: 0 auto; }
header.top h1 { font-size: clamp(1.7rem, 5vw, 2.4rem); line-height: 1.1; margin: 0 0 6px; letter-spacing: -0.01em; text-wrap: balance; }
header.top p { margin: 0; opacity: .92; max-width: 60ch; }
header.top p.how { margin-top: 8px; font-weight: 600; opacity: 1; }
.facts { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; padding: 0; list-style: none; }
.facts li { background: rgba(255,255,255,.14); border-radius: 999px; padding: 4px 12px; font-size: .88rem; font-variant-numeric: tabular-nums; }
nav.tabs { position: sticky; top: env(safe-area-inset-top, 0px); z-index: 20; background: var(--bg); border-bottom: 1px solid var(--line);
  margin-inline: calc(-1 * max(16px, env(safe-area-inset-left, 0px))); padding: 8px max(16px, env(safe-area-inset-left, 0px)); overflow-x: auto; white-space: nowrap; }
nav.tabs a { display: inline-block; padding: 6px 12px; margin-right: 4px; border-radius: 999px; color: var(--fg); text-decoration: none; font-size: .9rem; border: 1px solid transparent; }
nav.tabs a:hover, nav.tabs a:focus-visible { border-color: var(--line); background: var(--panel); outline: none; }
section { padding-top: 40px; }
section > h2 { font-size: 1.5rem; line-height: 1.2; margin: 0 0 6px; text-wrap: balance; letter-spacing: -0.01em; }
section > .sub { color: var(--muted); margin: 0 0 18px; max-width: 62ch; }
h3 { font-size: 1.08rem; margin: 22px 0 8px; }
h4 { font-size: .95rem; margin: 22px 0 6px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
p { margin: 0 0 12px; }
.lead { max-width: 66ch; }
.muted { color: var(--muted); font-size: .9rem; }
a { color: var(--accent); text-underline-offset: 2px; }
a:focus-visible, button:focus-visible, summary:focus-visible, input:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; border-radius: 4px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap: 14px; }
.finding { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 18px; box-shadow: var(--shadow); min-width: 0; }
.finding .big { font-size: 2rem; font-weight: 750; color: var(--accent); line-height: 1; font-variant-numeric: tabular-nums; letter-spacing: -0.02em; overflow-wrap: anywhere; }
.finding h3 { margin: 8px 0 8px; font-size: 1.05rem; text-wrap: balance; }
.finding p { font-size: .95rem; }
.caveat { color: var(--muted); font-size: .88rem; }
.src { font-size: .82rem; color: var(--muted); margin: 8px 0 0; }
.chip { display: inline-block; font-family: var(--mono); font-size: .76rem; padding: 1px 7px; margin: 0 3px 3px 0; border: 1px solid var(--line); border-radius: 999px; color: var(--muted); text-decoration: none; }
.chip:hover { color: var(--accent); border-color: var(--accent); }
.todos { list-style: none; padding: 0; margin: 0 0 12px; display: grid; gap: 10px; }
.todo { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
.todo-head { display: flex; gap: 12px; align-items: flex-start; cursor: pointer; }
.todo-head input { width: 22px; height: 22px; margin-top: 2px; accent-color: var(--accent); flex: none; }
.todo-title { font-weight: 650; }
.todo.done .todo-title { text-decoration: line-through; color: var(--muted); }
.why { color: var(--muted); font-size: .92rem; margin: 6px 0 0 34px; }
.todo details { margin: 6px 0 0 34px; }
.progress { display: flex; align-items: center; gap: 12px; font-size: .92rem; color: var(--muted); }
.track { display: block; flex: 1; height: 8px; background: var(--none-soft); border-radius: 999px; overflow: hidden; min-width: 80px; }
.track > span, #progress-bar { display: block; height: 100%; background: var(--accent); border-radius: 999px; }
#progress-bar { width: 0; transition: width .25s; }
.track.warm > span { background: var(--accent); }
summary { cursor: pointer; font-weight: 600; padding: 4px 0; }
details > summary::marker { color: var(--muted); }
.filters { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0; }
.fchip { font: inherit; font-size: .88rem; padding: 6px 12px; border-radius: 999px; border: 1px solid var(--line); background: var(--panel); color: var(--fg); cursor: pointer; }
.fchip.on { background: var(--fg); color: var(--bg); border-color: var(--fg); }
.scroll { overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); }
.tbl { width: 100%; border-collapse: collapse; font-size: .92rem; }
.tbl th { text-align: left; font-size: .78rem; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); padding: 10px 12px; border-bottom: 1px solid var(--line); white-space: nowrap; }
.tbl td { padding: 9px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }
.tbl tr:last-child td { border-bottom: 0; }
.tbl td.wrap { min-width: 220px; }
.tbl td.num { text-align: right; font-variant-numeric: tabular-nums; font-family: var(--mono); }
.tbl td.mine { color: var(--accent); font-weight: 700; }
.host { color: var(--muted); font-size: .8rem; font-family: var(--mono); overflow-wrap: anywhere; }
.pill { display: inline-block; font-size: .78rem; font-weight: 650; padding: 2px 9px; border-radius: 999px; white-space: nowrap; }
.pill.ok { background: var(--ok-soft); color: var(--ok); }
.pill.warn { background: var(--warn-soft); color: var(--warn); }
.pill.stop { background: var(--stop-soft); color: var(--stop); }
.pill.none { background: var(--none-soft); color: var(--muted); }
.pill.lab { background: var(--none-soft); color: var(--muted); font-weight: 500; }
.tag { font-size: .74rem; padding: 1px 8px; border-radius: 999px; background: var(--none-soft); color: var(--muted); margin-left: 6px; }
ul.bars { list-style: none; padding: 0; margin: 8px 0 16px; display: grid; gap: 10px; }
.bar-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 8px; }
.bar-head .val { margin-left: auto; font-variant-numeric: tabular-nums; font-family: var(--mono); font-size: .86rem; color: var(--muted); }
.bars .note { font-size: .82rem; color: var(--muted); margin-top: 2px; }
ul.plain, ul.open { padding-left: 20px; }
ul.plain li, ul.open li { margin-bottom: 8px; }
ul.open { list-style: none; padding: 0; display: grid; gap: 10px; }
ul.open li { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; margin: 0; }
.need { color: var(--accent); font-weight: 600; }
blockquote { margin: 10px 0; padding: 10px 14px; border-left: 4px solid var(--accent); background: var(--accent-soft); border-radius: 0 8px 8px 0; }
blockquote p { margin: 0 0 4px; }
blockquote footer { font-size: .82rem; color: var(--muted); }
details.topic { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 8px 14px; margin-bottom: 8px; }
details.topic .tname { font-weight: 650; margin-right: 6px; }
details.topic > summary { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; list-style: none; }
details.topic > summary::-webkit-details-marker { display: none; }
details.topic > summary::after { content: ""; margin-left: auto; flex: none; width: 8px; height: 8px; border-right: 2px solid var(--muted); border-bottom: 2px solid var(--muted); transform: rotate(45deg); transition: transform .15s; }
details.topic[open] > summary::after { transform: rotate(225deg); }
.tbody { padding: 6px 0 4px; }
.tbody p { font-size: .94rem; margin-bottom: 8px; }
.draft { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; margin-bottom: 12px; }
.draft header { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; }
.draft h3 { margin: 0; font-size: 1.02rem; flex: 1 1 240px; }
.kind { font-size: .74rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.approve { background: var(--warn-soft); color: var(--fg); border-radius: 8px; padding: 8px 12px; font-size: .9rem; margin: 10px 0; }
pre.text { white-space: pre-wrap; overflow-wrap: anywhere; font-family: var(--font); font-size: .93rem; line-height: 1.5; background: var(--bg); border: 1px solid var(--line); border-radius: 8px; padding: 12px; margin: 8px 0; max-height: 60vh; overflow: auto; }
button.copy { font: inherit; font-weight: 650; padding: 8px 16px; border-radius: 8px; border: 0; background: var(--fg); color: var(--bg); cursor: pointer; }
button.copy.ok { background: var(--ok); color: #fff; }
.issues { padding-left: 18px; font-size: .9rem; }
.issues li { margin-bottom: 6px; }
ol.links { padding-left: 0; list-style: none; font-size: .9rem; margin: 6px 0 12px; }
ol.links li { display: flex; gap: 8px; margin-bottom: 4px; align-items: baseline; flex-wrap: wrap; }
.rk { font-family: var(--mono); color: var(--muted); min-width: 1.6em; text-align: right; }
mark { background: var(--stop-soft); color: var(--stop); padding: 0 3px; border-radius: 3px; }
footer.end { margin-top: 48px; padding-top: 16px; border-top: 1px solid var(--line); color: var(--muted); font-size: .88rem; }
.callout { background: var(--accent-soft); border-left: 4px solid var(--accent); border-radius: 0 10px 10px 0; padding: 2px 16px 10px; margin: 16px 0; }
.callout h3 { margin: 12px 0 6px; }
ul.picks { list-style: none; padding: 0; margin: 10px 0 18px; display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 290px), 1fr)); gap: 14px; }
.pick { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 16px 18px; box-shadow: var(--shadow); display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.pick .big-claim { font-size: 1.3rem; line-height: 1.25; font-weight: 720; letter-spacing: -0.01em; text-wrap: balance; margin: 0; overflow-wrap: anywhere; }
.pick .pwhy { color: var(--muted); font-size: .92rem; margin: 0; }
.pick .approve { margin: 0; }
.pick .cmeta { margin-top: auto; }
ul.claims { list-style: none; padding: 0; margin: 10px 0; display: grid; gap: 8px; }
li.claim { background: var(--bg); border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; min-width: 0; }
.ctext { font-weight: 620; margin: 0 0 8px; overflow-wrap: anywhere; }
.cmeta { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.cmeta .tag { margin-left: 0; }
.cmeta button.copy { margin-left: auto; padding: 8px 14px; font-size: .88rem; min-height: 40px; }
li.claim .approve, li.claim .muted { margin: 8px 0 0; }
li.claim .cmeta button.copy { background: transparent; color: var(--fg); border: 1px solid var(--line); font-weight: 600; }
li.claim .cmeta button.copy:hover { border-color: var(--accent); }
li.claim .cmeta button.copy.ok { background: var(--ok); color: #fff; border-color: var(--ok); }
.evi { border-top: 1px solid var(--line); padding-top: 8px; margin-top: 8px; }
header.top p.newlink { margin-top: 12px; }
header.top p.newlink a { display: inline-block; padding: 8px 16px; border-radius: 999px; background: #fff; color: var(--head-a); font-weight: 650; text-decoration: none; }
@media (max-width: 520px) { section { padding-top: 32px; } .finding .big { font-size: 1.7rem; }
  .tbl.stack thead { display: none; } .tbl.stack, .tbl.stack tbody, .tbl.stack tr, .tbl.stack td { display: block; width: 100%; }
  .tbl.stack tr { padding: 10px 12px; border-bottom: 1px solid var(--line); } .tbl.stack tr[hidden] { display: none; }
  .tbl.stack td { border: 0; padding: 2px 0; } .tbl.stack td.wrap { min-width: 0; }
  .tbl.stack td::before { content: attr(data-label); display: block; font-size: .72rem; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); } }
@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } #progress-bar { transition: none; } details.topic > summary::after { transition: none; } }
"""

JS = """
(function () {
  var KEY = 'mito-radar-checks-' + document.getElementById('radar').getAttribute('data-snapshot');
  function load() { try { return JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { return {}; } }
  function save(v) { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch (e) { /* storage may be blocked */ } }
  var state = load();
  var boxes = document.querySelectorAll('.todo input[type=checkbox]');
  function paint() {
    var done = 0;
    boxes.forEach(function (b) { var id = b.closest('.todo').getAttribute('data-id'); b.checked = !!state[id]; b.closest('.todo').classList.toggle('done', b.checked); if (b.checked) done++; });
    var t = document.getElementById('progress-text'); if (t) t.textContent = 'Splněno ' + done + ' z ' + boxes.length;
    var bar = document.getElementById('progress-bar'); if (bar) bar.style.width = (boxes.length ? 100 * done / boxes.length : 0) + '%';
  }
  boxes.forEach(function (b) { b.addEventListener('change', function () { state[b.closest('.todo').getAttribute('data-id')] = b.checked; save(state); paint(); }); });
  paint();
  var chips = document.querySelectorAll('.fchip');
  document.querySelectorAll('.fchip').forEach(function (c) {
    c.addEventListener('click', function () {
      var f = c.getAttribute('data-filter');
      document.querySelectorAll('.fchip').forEach(function (x) { x.classList.toggle('on', x === c); });
      document.querySelectorAll('#vis tbody tr').forEach(function (r) { r.hidden = !(f === 'all' || r.getAttribute('data-group') === f); });
    });
  });
  if (window.innerWidth <= 520) { var first = document.querySelector('.fchip[data-filter=brand]'); if (first) first.click(); }
  document.querySelectorAll('button.copy').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var el = document.getElementById(btn.getAttribute('data-target'));
      var text = el.textContent;
      function done() { btn.classList.add('ok'); btn.textContent = 'Zkopírováno'; setTimeout(function () { btn.classList.remove('ok'); btn.textContent = 'Kopírovat text'; }, 1800); }
      function fallback() { var r = document.createRange(); r.selectNodeContents(el); var s = window.getSelection(); s.removeAllRanges(); s.addRange(r); btn.textContent = 'Text je označený, stiskněte Kopírovat'; }
      if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(text).then(done, fallback); } else { fallback(); }
    });
  });
  if (location.hash) { var t = document.getElementById(location.hash.slice(1)); if (t && t.tagName === 'DETAILS') t.open = true; }
  window.addEventListener('hashchange', function () { var t = document.getElementById(location.hash.slice(1)); if (t && t.tagName === 'DETAILS') t.open = true; });
})();
"""


def render_page(d: dict[str, Any], *, fragment: bool = False) -> str:
    m = d["meta"]
    facts = [f'{m["searches"]} skutečných hledání', f'{m["links"]} odkazů z {m["hosts"]} webů', f'{d["science"]["verified"]} z {d["science"]["total"]} ověřených studií', "0 simulovaných údajů"]
    nav = [("zjisteni", "Zjištění"), ("ukoly", "Úkoly"), ("videt", "Kde jste vidět"), ("trh", "Trh"), ("znacka", "Vaše značka"), ("temata", "Témata"),
           ("tvrzeni", "Co smíte tvrdit"), ("claimy", "Emoční claimy"), ("navrhy", "Návrhy textů"), ("studie", "Studie"), ("chybi", "Co chybí"), ("data", "Jak jsou data získaná")]
    nav_html = "".join(f'<a href="#{i}">{esc(t)}</a>' for i, t in nav)
    body = f'''<div id="radar" data-snapshot="{esc(m["date"])}">
<header class="top"><div class="in">
  <h1>MITO LIGHT Radar</h1>
  <p>Co o značce a trhu ukazuje skutečné vyhledávání na webu ke dni {esc(m["date_cs"])}, co z toho plyne a co napsat jako první.</p>
  <p class="how">Začněte zjištěními a úkoly. Zbytek stránky jsou důkazy a hotové texty.</p>
  <p class="newlink"><a href="#claimy">Nově: emoční claimy, {C.count(d["emotion"]["totals"]["claims"], "hotová věta", "hotové věty", "hotových vět")}</a></p>
  <ul class="facts">{"".join(f"<li>{esc(f)}</li>" for f in facts)}</ul>
</div></header>
<nav class="tabs" aria-label="Obsah">{nav_html}</nav>
<main class="wrap-page">
<section id="zjisteni"><h2>Co z dat plyne</h2><p class="sub">Sedm zjištění. Každé má číslo, větu, upozornění a odkaz na hledání, ze kterého vychází.</p>{render_findings(d)}</section>
<section id="ukoly"><h2>Co udělat tento týden</h2><p class="sub">Šest kroků v pořadí důležitosti. Zaškrtnutí se pamatuje jen v tomto prohlížeči.</p>{render_actions(d)}</section>
<section id="videt"><h2>Kde jste vidět</h2><p class="sub">Co se stalo při hledání z pohledu zákazníka.</p>{render_visibility(d)}</section>
<section id="trh"><h2>Kdo je kolem vás</h2><p class="sub">Weby, které se ve výsledcích opakují.</p>{render_landscape(d)}</section>
<section id="znacka"><h2>Jak vás vidí vyhledávače a AI</h2><p class="sub">Název MITO LIGHT je podobný jiné značce. Tady je vidět, co z toho ve výsledcích plyne.</p>{render_identity(d)}</section>
<section id="temata"><h2>Co zveřejňují úspěšné značky</h2><p class="sub">Porovnání témat výrobců, recenzních webů a vašeho webu.</p>{render_themes(d)}</section>
<section id="tvrzeni"><h2>Co smíte tvrdit</h2><p class="sub">Mapa tvrzení: síla důkazů se počítá jen z ověřených studií.</p>{render_claim_map(d)}
<h3>Názvy vašich stránek</h3>{render_own_titles(d)}
<h3>Co o sobě tvrdí trh</h3>{render_market_claims(d)}</section>
<section id="claimy"><h2>Emoční claimy</h2><p class="sub">Pozitivní věty o těšení, rituálu, příběhu a volbě. Žádná netvrdí účinek na tělo.</p>{render_claims(d)}</section>
<section id="navrhy"><h2>Návrhy textů</h2><p class="sub">Napsal je Claude podle zadání a faktů značky. Každý prošel kontrolou tvrzení. Jsou to koncepty, před zveřejněním je musí přečíst člověk. Obsah vytvořený s pomocí AI může podle pravidel platforem a evropského nařízení o AI vyžadovat označení; ověřte si pravidla, která se vás týkají (nejde o právní poradenství).</p>{render_drafts(d)}</section>
<section id="studie"><h2>Studie za mapou tvrzení</h2>{render_science(d)}</section>
<section id="chybi"><h2>Co chybí a co je potřeba</h2><p class="sub">Radar nevidí všechno. Tady je přesně co a proč.</p>{render_open(d)}</section>
<section id="data"><h2>Jak jsou data získaná</h2>{render_method(d)}</section>
<footer class="end">MITO LIGHT Radar, verze 2.0. Snímek {esc(m["first"])} až {esc(m["last"])}. Zdroj dat: {esc(m["tool"])} s vyhledáváním na webu.</footer>
</main>
</div>'''
    if fragment:
        return normalize_dashes(f'''<meta name="claude:viewport-fit-sides" content="cover">
<title>MITO LIGHT Radar</title>
<style>{CSS}</style>
{body}
<script>{JS}</script>
''')
    page = f'''<!doctype html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="claude:viewport-fit-sides" content="cover">
<title>MITO LIGHT Radar</title>
<style>{CSS}</style>
</head>
<body>
{body}
<script>{JS}</script>
</body>
</html>
'''
    return normalize_dashes(page)


def build_report(snapshot: str | Path, drafts: str | Path, out: str | Path, *, plan_path: str | Path, fragment: bool = False) -> Path:
    data = report_data(snapshot, drafts, plan_path)
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_page(data, fragment=fragment), "utf-8")
    return out_path
