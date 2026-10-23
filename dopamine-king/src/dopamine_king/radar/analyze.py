"""From stored search records to the numbers of the report.

Pure functions over the records ``collect`` stored plus two small curated files (domains and themes). No network, no model, no
random numbers: the same snapshot always gives the same report. Every number can be traced to the links that produced it.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import unquote, urlsplit

from ..scoring import fold

MARKET_GROUPS = ("category", "persona", "competitor")           # what a Czech buyer searches for
VISIBILITY_GROUPS = ("brand", "category", "persona", "competitor")
JUNK_TITLES = {"hlavni obsah", "table of contents", "skupina produktu:", "home", "homepage", "menu", "passa al contenuto", "background preloader"}
SCHOLARLY_HOSTS = ("pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "europepmc.org", "doi.org", "cochranelibrary.com", "mdpi.com",
                   "sciencedirect.com", "onlinelibrary.wiley.com", "link.springer.com", "springer.com", "tandfonline.com", "liebertpub.com",
                   "journals.sagepub.com", "academic.oup.com", "nature.com", "frontiersin.org", "journals.lww.com", "jamanetwork.com",
                   "bmj.com", "thelancet.com", "karger.com", "scielo.br", "semanticscholar.org", "researchgate.net", "jlms.sbmu.ac.ir",
                   "journals.sbmu.ac.ir", "aesthetic-surgery-journal.com", "wiley.com", "elsevier.com", "plos.org", "pmc.ncbi.nlm.nih.gov")
RULE_NAMES_CS = {
    "CLAIM_MEDICAL": "zdravotní tvrzení (léčí, zmírňuje)",
    "CLAIM_AVOID": "rizikové nebo nepodložené tvrzení",
    "DISEASE_MENTION": "nemoc vedle slova o léčbě či přínosu",
    "STATUS_CLAIM": "tvrzení o regulačním statusu",
    "SAFETY_ABSOLUTE": "absolutní tvrzení o bezpečnosti",
    "MEDICATION_ADVICE": "rada ohledně léků",
}
ERROR_RULES = tuple(RULE_NAMES_CS)


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
    parts = urlsplit(url)
    segments = [unquote(s) for s in parts.path.split("/") if s and s.lower() not in ("index.html", "index.php")]
    last = segments[-1] if segments else ""
    last = re.sub(r"\.(html?|php|pdf|aspx?)$", "", last, flags=re.I)
    words = re.sub(r"[-_+]+", " ", last).strip()
    words = re.sub(r"^\d{3,}\s+", "", words)                   # leading ids such as 2385920
    return words


def title_is_junk(title: str, url: str) -> bool:
    plain = fold(title.strip().lower())
    if len(plain) < 4 or not re.search(r"[a-z]", plain):
        return True
    if plain in JUNK_TITLES or plain.startswith("[date") or re.fullmatch(r"[\w.-]+\.[a-z]{2,}", plain):
        return True
    return False


def display(link: dict[str, Any]) -> dict[str, Any]:
    """Title to show: the page's own title when it says something, otherwise words taken from the address (marked)."""
    title = link["title"].strip()
    if not title_is_junk(title, link["url"]):
        return {"label": title, "derived": False}
    words = slug_label(link["url"])
    return {"label": words or host_of(link["url"]), "derived": True}


def load_config(folder: str | Path) -> dict[str, Any]:
    root = Path(folder)
    return {"domains": json.loads((root / "domains.json").read_text("utf-8")),
            "themes": json.loads((root / "themes.json").read_text("utf-8"))}


def domain_info(host: str, domains_cfg: dict[str, Any]) -> dict[str, Any]:
    entries = domains_cfg.get("domains", {})
    for key in (host, *[host.split(".", i)[-1] for i in range(1, host.count("."))]):
        if key in entries:
            return entries[key]
    return {}


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
            "confusable_links": sum(host_matches(host_of(l["url"]), confusable) for l in links),
            "top": {"host": host_of(first["url"]), "title": display(first)["label"], "url": first["url"]} if first else None,
        })
    by_group: dict[str, dict[str, int]] = {}
    for g in VISIBILITY_GROUPS:
        sub = [r for r in rows if r["group"] == g]
        by_group[g] = {"queries": len(sub), "own": sum(r["own_rank"] is not None for r in sub),
                       "other_market": sum(r["other_market_rank"] is not None for r in sub)}
    market = [r for r in rows if r["group"] in MARKET_GROUPS]
    return {"rows": rows, "by_group": by_group,
            "market": {"queries": len(market), "own": sum(r["own_rank"] is not None for r in market),
                       "other_market": sum(r["other_market_rank"] is not None for r in market)}}


# -- who is around the brand -----------------------------------------------------------------------------------------------
def landscape(records: Sequence[dict[str, Any]], domains_cfg: dict[str, Any], *, min_queries: int = 2) -> dict[str, Any]:
    """Hosts in the results of the Czech market queries, with their curated type; hosts nobody classified stay apart."""
    stats: dict[str, dict[str, Any]] = {}
    for rec in records:
        if rec["group"] not in MARKET_GROUPS:
            continue
        for link in rec["links"]:
            host = host_of(link["url"])
            s = stats.setdefault(host, {"host": host, "queries": set(), "links": 0, "urls": {}, "best_rank": 99})
            s["queries"].add(rec["id"])
            s["links"] += 1
            s["best_rank"] = min(s["best_rank"], link["rank"])
            s["urls"].setdefault(link["url"], display(link)["label"])
    rows, unclassified, noise = [], [], 0
    for s in stats.values():
        info = domain_info(s["host"], domains_cfg)
        row = {"host": s["host"], "queries": len(s["queries"]), "links": s["links"], "best_rank": s["best_rank"],
               "type": info.get("type", ""), "name": info.get("name", s["host"]), "note": info.get("note", ""),
               "pages": [{"url": u, "label": t} for u, t in list(s["urls"].items())[:4]]}
        if info.get("type") == "noise":
            noise += s["links"]
        elif info:
            rows.append(row)
        elif len(s["queries"]) >= min_queries:
            unclassified.append(row)
    key = lambda r: (-r["queries"], -r["links"], r["host"])
    rows.sort(key=key)
    unclassified.sort(key=key)
    return {"domains": rows, "unclassified": unclassified, "noise_links": noise, "hosts": len(stats),
            "types": domains_cfg.get("types", {})}


# -- identity of the brand in the results ------------------------------------------------------------------------------------
def identity(records: Sequence[dict[str, Any]], brand: dict[str, Any], domains_cfg: dict[str, Any]) -> dict[str, Any]:
    """Pages about the brand outside its own sites, and how much of a brand query goes to the look-alike brand."""
    own = set(brand["own_domains"]) | set(brand.get("related_domains", []))
    confusable_domains = {d for d in brand.get("confusable", []) if "." in d}
    names = [fold(n.lower()) for n in [brand["name"], *brand.get("aliases", [])]]
    about: dict[str, dict[str, Any]] = {}
    brand_rows = []
    for rec in records:
        if rec["group"] != "brand":
            continue
        named = rec["query"].lower().startswith(("mito light", "mitolight"))
        links = rec["links"]
        lookalike = [l for l in links if host_matches(host_of(l["url"]), confusable_domains)]
        brand_rows.append({"id": rec["id"], "query": rec["query"], "links": len(links), "lookalike": len(lookalike),
                           "named": named and "nebo" not in rec["query"].lower()})
        for link in links:
            host = host_of(link["url"])
            if host_matches(host, own) or host_matches(host, confusable_domains):
                continue
            text = fold((link["title"] + " " + link["url"]).lower()).replace("-", " ").replace("_", " ")
            if any(n in text for n in names) and domain_info(host, domains_cfg).get("type") != "noise":
                entry = about.setdefault(link["url"], {"host": host, "title": display(link)["label"], "url": link["url"], "queries": []})
                entry["queries"].append(rec["id"])
    named_rows = [r for r in brand_rows if r["named"]]
    total = sum(r["links"] for r in named_rows)
    look = sum(r["lookalike"] for r in named_rows)
    return {"about": sorted(about.values(), key=lambda e: (-len(e["queries"]), e["host"])), "rows": brand_rows,
            "lookalike_links": look, "named_links": total,
            "worst": max(named_rows, key=lambda r: r["lookalike"], default=None)}


# -- what the top brands publish ---------------------------------------------------------------------------------------------
def theme_ids(text: str, url: str, themes_cfg: dict[str, Any]) -> list[str]:
    haystack = " " + " ".join(_tokens(text + " " + slug_label(url) + " " + urlsplit(url).path)) + " "
    found = []
    for theme in themes_cfg["themes"]:
        if any(" " + " ".join(_tokens(k)) + " " in haystack or (k.endswith("*") and " " + " ".join(_tokens(k[:-1])) in haystack)
               for k in theme["keywords"]):
            found.append(theme["id"])
    return found


def brandsites(records: Sequence[dict[str, Any]], themes_cfg: dict[str, Any]) -> dict[str, Any]:
    sites = []
    counts: Counter[str] = Counter()
    brands_per_theme: dict[str, set[str]] = defaultdict(set)
    for rec in records:
        if rec["group"] != "brandsite":
            continue
        domain = (rec.get("allowed_domains") or [""])[0]
        pages = []
        for link in rec["links"]:
            if not host_matches(host_of(link["url"]), [domain]):
                continue
            shown = display(link)
            found = theme_ids(shown["label"], link["url"], themes_cfg)
            pages.append({"url": link["url"], "label": shown["label"], "derived": shown["derived"], "themes": found})
            for t in found:
                counts[t] += 1
                brands_per_theme[t].add(domain)
        sites.append({"id": rec["id"], "domain": domain, "purpose": rec.get("purpose", ""), "pages": pages})
    labels = {t["id"]: t["name_cs"] for t in themes_cfg["themes"]}
    return {"sites": sites, "pages": sum(len(s["pages"]) for s in sites),
            "themes": [{"id": t["id"], "name": labels[t["id"]], "pages": counts[t["id"]], "brands": len(brands_per_theme[t["id"]])}
                       for t in themes_cfg["themes"]]}


# -- claims found in real page titles ----------------------------------------------------------------------------------------
def claims_audit(records: Sequence[dict[str, Any]], profile: Any, domains_cfg: dict[str, Any], *, own_domains: Sequence[str] = ()) -> dict[str, Any]:
    """Run the claims profile over the titles of pages the search returned: the page's own words, never the machine summary."""
    seen: set[str] = set()
    scanned = 0
    flagged: list[dict[str, Any]] = []
    for rec in records:
        if rec["group"] in ("study", "own"):
            continue
        for link in rec["links"]:
            url = link["url"]
            host = host_of(url)
            if url in seen or host_matches(host, own_domains) or domain_info(host, domains_cfg).get("type") == "noise":
                continue
            seen.add(url)
            if title_is_junk(link["title"], url):
                continue
            scanned += 1
            hits = [h for h in profile.scan_text(link["title"]) if h.code in ERROR_RULES]
            if hits:
                h = hits[0]
                flagged.append({"host": host, "title": link["title"], "url": url, "code": h.code, "rule": RULE_NAMES_CS[h.code],
                                "fragment": link["title"][h.start:h.end], "topic": h.topic.name_cs if h.topic else "", "query": rec["id"]})
    codes = Counter(f["code"] for f in flagged)
    return {"scanned": scanned, "flagged": len(flagged), "by_rule": {RULE_NAMES_CS[c]: n for c, n in codes.most_common()}, "examples": flagged}


# -- the study leads --------------------------------------------------------------------------------------------------------
def study_check(records: Sequence[dict[str, Any]], studies: Sequence[Any]) -> list[dict[str, Any]]:
    """For every unverified study of the ledger: was its exact title found on a page, and on what kind of site."""
    by_id = {s.id: s for s in studies}
    rows = []
    for rec in records:
        if rec["group"] != "study":
            continue
        study_id = rec.get("study_id") or rec["purpose"].rsplit(": ", 1)[-1]
        study = by_id.get(study_id)
        if study is None:
            continue
        want = set(_tokens(study.title))
        best, best_cov = None, 0.0
        for link in rec["links"]:
            have = set(_tokens(link["title"] + " " + slug_label(link["url"])))
            cov = len(want & have) / len(want) if want else 0.0
            if cov > best_cov:
                best, best_cov = link, cov
        scholarly = bool(best) and host_matches(host_of(best["url"]), SCHOLARLY_HOSTS)
        rows.append({"study_id": study_id, "title": study.title, "coverage": round(best_cov, 2),
                     "found": best_cov >= 0.8, "scholarly": scholarly,
                     "url": best["url"] if best and best_cov >= 0.5 else "", "host": host_of(best["url"]) if best and best_cov >= 0.5 else ""})
    return rows
