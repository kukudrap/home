"""From stored search records to the numbers of the report.

Pure functions over the records ``collect`` stored plus three small curated files (domains, themes, outcome words). No network, no
model, no random numbers: the same snapshot always gives the same report. Every number can be traced to the links that produced it.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import unquote, urlsplit

from ..generate.claims import terms_regex
from ..generate.seo import split_sentences
from ..scoring import fold

MARKET_GROUPS = ("category", "persona", "competitor")           # what a Czech buyer searches for
VISIBILITY_GROUPS = ("brand", "category", "persona", "competitor")
JUNK_TITLES = {"hlavni obsah", "table of contents", "skupina produktu:", "home", "homepage", "menu", "passa al contenuto", "background preloader"}
JUNK_PREFIXES = ("[date", "an image of", "picture of", "image of", "to the page content", "- ")
JUNK_RE = re.compile(r"^[-\s]*\d+\s*min(?:ute)?s?\s+read$")
AUDIT_TYPES = ("media", "pharmacy", "ecommerce", "service", "foreign_shop", "foreign_media", "maker")   # hosts that sell or promote
RULE_NAMES_CS = {
    "CLAIM_MEDICAL": "zdravotní tvrzení (léčí, zmírňuje)",
    "CLAIM_AVOID": "rizikové nebo nepodložené tvrzení",
    "DISEASE_MENTION": "nemoc vedle slova o léčbě či přínosu",
    "STATUS_CLAIM": "tvrzení o regulačním statusu",
    "SAFETY_ABSOLUTE": "absolutní tvrzení o bezpečnosti",
    "MEDICATION_ADVICE": "rada ohledně léků",
}
ERROR_RULES = tuple(RULE_NAMES_CS)
LIGHT_WORDS = ("svetl", "light", " led", "infra", "panel", "photobio", "fotobio", "laser", "lamp", "terapi", "therap", "mito", "maska", "mask")


# -- small helpers -------------------------------------------------------------------------------------------------------
def host_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def host_matches(host: str, domains: Iterable[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text.lower()))


def slug_label(url: str) -> str:
    """Readable words from the last meaningful part of a URL, used only when the page title says nothing."""
    segments = [unquote(s) for s in urlsplit(url).path.split("/") if s and s.lower() not in ("index.html", "index.php")]
    last = re.sub(r"\.(html?|php|pdf|aspx?)$", "", segments[-1] if segments else "", flags=re.I)
    return re.sub(r"^\d{3,}\s+", "", re.sub(r"[-_+]+", " ", last).strip())


def title_is_junk(title: str, url: str = "") -> bool:
    plain = fold(title.strip().lower())
    if len(plain) < 4 or not re.search(r"[a-z]", plain):
        return True
    return (plain in JUNK_TITLES or plain.startswith(JUNK_PREFIXES) or bool(JUNK_RE.match(plain))
            or bool(re.fullmatch(r"[\w.-]+\.[a-z]{2,}", plain)))


def display(link: dict[str, Any]) -> dict[str, Any]:
    """Title to show: the page's own title when it says something, otherwise words taken from the address (marked)."""
    title = link["title"].strip()
    if not title_is_junk(title, link["url"]):
        return {"label": title, "derived": False}
    return {"label": slug_label(link["url"]) or host_of(link["url"]), "derived": True}


def load_config(folder: str | Path, brands: dict[str, Any] | None = None) -> dict[str, Any]:
    """The curated files of the radar; the brand registry of the vertical adds the makers and review sites it lists."""
    root = Path(folder)
    domains = json.loads((root / "domains.json").read_text("utf-8"))
    entries = dict(domains["domains"])
    for brand in (brands or {}).get("brands", []):
        host = host_of(brand.get("homepage", ""))
        if host and host not in entries:
            kind = "foreign_media" if brand.get("category") == "media" else "science" if brand.get("category") == "association" else "maker"
            entries[host] = {"type": kind, "name": brand.get("name", host)}
    return {"domains": {**domains, "domains": entries}, "themes": json.loads((root / "themes.json").read_text("utf-8")),
            "outcome": json.loads((root / "outcome_words.json").read_text("utf-8"))}


def domain_info(host: str, domains_cfg: dict[str, Any]) -> dict[str, Any]:
    entries = domains_cfg.get("domains", {})
    parts = host.split(".")
    for i in range(len(parts) - 1):
        key = ".".join(parts[i:])
        if key in entries:
            return entries[key]
    return {}


def is_light_related(text: str) -> bool:
    folded = " " + fold(text.lower())
    return any(word in folded for word in LIGHT_WORDS)


# -- visibility ----------------------------------------------------------------------------------------------------------
def visibility(records: Sequence[dict[str, Any]], brand: dict[str, Any]) -> dict[str, Any]:
    own, other = set(brand["own_domains"]), set(brand.get("related_domains", []))
    confusable = {d for d in brand.get("confusable", []) if "." in d}
    rows = []
    for rec in records:
        if rec["group"] not in VISIBILITY_GROUPS:
            continue
        links = rec["links"]
        own_ranks = [l["rank"] for l in links if host_matches(host_of(l["url"]), own)]
        other_ranks = [l["rank"] for l in links if host_matches(host_of(l["url"]), other)]
        first = links[0] if links else None
        rows.append({
            "id": rec["id"], "group": rec["group"], "persona": rec.get("persona", ""), "query": rec["query"], "purpose": rec.get("purpose", ""),
            "n_links": len(links), "own_rank": min(own_ranks) if own_ranks else None, "other_market_rank": min(other_ranks) if other_ranks else None,
            "lookalike_links": sum(host_matches(host_of(l["url"]), confusable) for l in links),
            "top": {"host": host_of(first["url"]), "title": display(first)["label"], "url": first["url"]} if first else None,
        })
    by_group = {g: {"queries": sum(r["group"] == g for r in rows), "own": sum(r["group"] == g and r["own_rank"] is not None for r in rows)}
                for g in VISIBILITY_GROUPS}
    market = [r for r in rows if r["group"] in MARKET_GROUPS]
    return {"rows": rows, "by_group": by_group,
            "market": {"queries": len(market), "own": sum(r["own_rank"] is not None for r in market)},
            "all": {"queries": len(rows), "own": sum(r["own_rank"] is not None for r in rows),
                    "other_market": sum(r["other_market_rank"] is not None for r in rows)}}


# -- who is around the brand -----------------------------------------------------------------------------------------------
def landscape(records: Sequence[dict[str, Any]], domains_cfg: dict[str, Any]) -> dict[str, Any]:
    """Hosts in the results of the Czech market queries, with their curated type. Hosts nobody classified are only counted."""
    stats: dict[str, dict[str, Any]] = {}
    for rec in records:
        if rec["group"] not in MARKET_GROUPS:
            continue
        for link in rec["links"]:
            host = host_of(link["url"])
            s = stats.setdefault(host, {"host": host, "queries": set(), "links": 0, "urls": {}})
            s["queries"].add(rec["id"])
            s["links"] += 1
            s["urls"].setdefault(link["url"], display(link)["label"])
    rows, unclassified, noise = [], 0, 0
    for s in stats.values():
        info = domain_info(s["host"], domains_cfg)
        if info.get("type") == "noise":
            noise += s["links"]
        elif info.get("type") == "science":
            continue                                       # literature and patents are not who surrounds the brand
        elif not info:
            unclassified += s["links"]
        else:
            rows.append({"host": s["host"], "queries": len(s["queries"]), "links": s["links"], "type": info["type"],
                         "name": info.get("name", s["host"]), "note": info.get("note", ""),
                         "pages": [{"url": u, "label": t} for u, t in list(s["urls"].items())[:3]]})
    rows.sort(key=lambda r: (-r["queries"], -r["links"], r["host"]))
    total = sum(s["links"] for s in stats.values())
    return {"domains": rows, "types": domains_cfg.get("types", {}), "links": total, "noise_links": noise, "unclassified_links": unclassified,
            "hosts": len(stats)}


# -- identity of the brand in the results ------------------------------------------------------------------------------------
def identity(records: Sequence[dict[str, Any]], brand: dict[str, Any], domains_cfg: dict[str, Any],
             direct: Sequence[dict[str, Any]] = ()) -> dict[str, Any]:
    """Pages about the brand outside its own sites, how much of a brand query goes to the look-alike brand, and what summaries claim."""
    own = set(brand["own_domains"]) | set(brand.get("related_domains", []))
    look_domains = {d for d in brand.get("confusable", []) if "." in d}
    look_names = [fold(n.lower()) for n in brand.get("confusable", []) if "." not in n]
    names = [fold(n.lower()) for n in [brand["name"], *brand.get("aliases", [])]]
    about: dict[str, dict[str, Any]] = {}
    rows = []
    quotes = []
    for rec in records:
        if rec["group"] != "brand":
            continue
        links = rec["links"]
        look = [l for l in links if host_matches(host_of(l["url"]), look_domains)]
        asks_comparison = " nebo " in rec["query"].lower()
        rows.append({"id": rec["id"], "query": rec["query"], "links": len(links), "lookalike": len(look), "counted": not asks_comparison})
        for link in links:
            host = host_of(link["url"])
            if host_matches(host, own) or host_matches(host, look_domains) or domain_info(host, domains_cfg).get("type") == "noise":
                continue
            text = fold((link["title"] + " " + link["url"]).lower()).replace("-", " ").replace("_", " ")
            if any(n in text for n in names):
                entry = about.setdefault(link["url"], {"host": host, "title": display(link)["label"], "url": link["url"], "queries": []})
                entry["queries"].append(rec["id"])
        for sentence in split_sentences(rec.get("summary", "")):
            folded = fold(sentence.lower())
            if any(n in folded for n in look_names) and any(n in folded for n in names):
                quotes.append({"id": rec["id"], "query": rec["query"], "text": sentence.strip(), "machine_summary": True})
    for rec in direct:
        sentence = rec.get("summary_sentence")
        if sentence:
            quotes.append({"id": rec["id"], "query": rec["query"], "text": sentence, "machine_summary": True})
    counted = [r for r in rows if r["counted"]]
    return {"about": sorted(about.values(), key=lambda e: (-len(e["queries"]), e["host"])), "rows": rows,
            "lookalike_links": sum(r["lookalike"] for r in counted), "counted_links": sum(r["links"] for r in counted),
            "worst": max(counted, key=lambda r: r["lookalike"], default=None), "quotes": quotes}


# -- what the top brands publish ---------------------------------------------------------------------------------------------
def theme_ids(text: str, url: str, themes_cfg: dict[str, Any]) -> list[str]:
    haystack = " " + " ".join(_tokens(text + " " + slug_label(url) + " " + urlsplit(url).path)) + " "
    found = []
    for theme in themes_cfg["themes"]:
        for keyword in theme["keywords"]:
            stem = keyword.endswith("*")
            phrase = " ".join(_tokens(keyword[:-1] if stem else keyword))
            if (" " + phrase) in haystack if stem else (" " + phrase + " ") in haystack:
                found.append(theme["id"])
                break
    return found


def brandsites(records: Sequence[dict[str, Any]], themes_cfg: dict[str, Any], domains_cfg: dict[str, Any]) -> dict[str, Any]:
    sites = []
    for rec in records:
        if rec["group"] != "brandsite":
            continue
        domain = (rec.get("allowed_domains") or [""])[0]
        kind = "maker" if domain_info(domain, domains_cfg).get("type") == "maker" else "media"
        pages = []
        for link in rec["links"]:
            if not host_matches(host_of(link["url"]), [domain]):
                continue
            shown = display(link)
            pages.append({"url": link["url"], "label": shown["label"], "derived": shown["derived"],
                          "themes": theme_ids(shown["label"], link["url"], themes_cfg)})
        sites.append({"id": rec["id"], "domain": domain, "kind": kind, "name": domain_info(domain, domains_cfg).get("name", domain), "pages": pages})
    themes = []
    for theme in themes_cfg["themes"]:
        row = {"id": theme["id"], "name": theme["name_cs"]}
        for kind in ("maker", "media"):
            matching = [s for s in sites if s["kind"] == kind and any(theme["id"] in p["themes"] for p in s["pages"])]
            row[kind] = {"pages": sum(theme["id"] in p["themes"] for s in sites if s["kind"] == kind for p in s["pages"]), "sites": len(matching)}
        row["examples"] = [{"site": s["name"], "title": p["label"], "url": p["url"]} for s in sites for p in s["pages"]
                           if theme["id"] in p["themes"] and not p["derived"]][:3]
        themes.append(row)
    return {"sites": sites, "pages": sum(len(s["pages"]) for s in sites), "sites_with_pages": sum(bool(s["pages"]) for s in sites),
            "makers": sum(s["kind"] == "maker" for s in sites), "media": sum(s["kind"] == "media" for s in sites), "themes": themes}


def own_pages(records: Sequence[dict[str, Any]], brand: dict[str, Any], themes_cfg: dict[str, Any]) -> dict[str, Any]:
    """Pages of the brand's own Czech site that the search tool knows, with their themes."""
    pages: dict[str, dict[str, Any]] = {}
    for rec in records:
        if rec["group"] != "own":
            continue
        for link in rec["links"]:
            if host_matches(host_of(link["url"]), brand["own_domains"]):
                url = re.sub(r"^https?://(?:www\.)?", "", link["url"]).rstrip("/")
                pages.setdefault(url, {"url": link["url"], "label": display(link)["label"], "themes": theme_ids(link["title"], link["url"], themes_cfg)})
    coverage = Counter(t for p in pages.values() for t in p["themes"])
    return {"pages": list(pages.values()), "themes": dict(coverage)}


# -- claims found in real page titles ----------------------------------------------------------------------------------------
def claims_audit(records: Sequence[dict[str, Any]], profile: Any, domains_cfg: dict[str, Any], *, own_domains: Sequence[str] = ()) -> dict[str, Any]:
    """Run the claims profile over the titles of pages that sell or promote light therapy: the page's own words, never a summary."""
    seen: set[str] = set()
    scanned = 0
    flagged: list[dict[str, Any]] = []
    for rec in records:
        if rec["group"] in ("study", "own"):
            continue
        for link in rec["links"]:
            url, title = link["url"], link["title"]
            host = host_of(url)
            if url in seen or host_matches(host, own_domains) or domain_info(host, domains_cfg).get("type") not in AUDIT_TYPES:
                continue
            seen.add(url)
            if title_is_junk(title, url) or title.rstrip().endswith("?") or not is_light_related(title + " " + url):
                continue                                   # questions are not claims; pages about something else are not our field
            scanned += 1
            hits = [h for h in profile.scan_text(title) if h.code in ERROR_RULES]
            if hits:
                h = hits[0]
                flagged.append({"host": host, "name": domain_info(host, domains_cfg).get("name", host), "title": title, "url": url, "code": h.code,
                                "rule": RULE_NAMES_CS[h.code], "fragment": title[h.start:h.end], "query": rec["id"]})
    codes = Counter(f["code"] for f in flagged)
    return {"scanned": scanned, "flagged": len(flagged), "by_rule": {RULE_NAMES_CS[c]: n for c, n in codes.most_common()}, "examples": flagged}


def outcome_titles(pages: Sequence[dict[str, Any]], profile: Any, claim_map: Sequence[dict[str, Any]], outcome_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Titles that name a body or performance topic together with an outcome word ("proti vráskám", "kvalitnější spánek").

    The claims profile is built around verbs, so a noun phrase such as "zvýšení množství vlasů" passes it. This second, simpler check
    reads titles only: a topic noun of the claim map plus a word that promises a result. It points to texts to review, it does not judge them.
    """
    words = outcome_cfg["words"]
    outcome_re = re.compile(terms_regex(words))
    by_id = {row["id"]: row for row in claim_map}
    rows = []
    for page in pages:
        low = fold(page["label"].lower())
        if not outcome_re.search(low):
            continue
        topics = [t for t in profile.topics if t.klass != "context" and t.nouns and re.search(terms_regex(t.nouns), low)]
        if topics:
            row = by_id.get(topics[0].id, {})
            rows.append({"url": page["url"], "title": page["label"], "topic": topics[0].name_cs, "topic_id": topics[0].id, "class": topics[0].klass,
                         "label": row.get("label", ""), "safe": (row.get("safe_cs") or [""])[0]})
    return rows


# -- direct cross-check -----------------------------------------------------------------------------------------------------
def validation(records: Sequence[dict[str, Any]], direct: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Overlap of the stored links with a search made directly with the tool, query by query."""
    by_id = {r["id"]: r for r in records}
    rows = []
    for d in direct:
        rec = by_id.get(d.get("compare_with", ""))
        if not rec:
            continue
        a, b = {l["url"] for l in rec["links"]}, {l["url"] for l in d["links"]}
        rows.append({"direct": d["id"], "query": d["query"], "stored": len(a), "direct_links": len(b), "shared": len(a & b),
                     "same_order": [l["url"] for l in rec["links"]] == [l["url"] for l in d["links"]]})
    return rows


def load_direct(snapshot: str | Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text("utf-8")) for p in sorted((Path(snapshot) / "direct").glob("*.json"))]
