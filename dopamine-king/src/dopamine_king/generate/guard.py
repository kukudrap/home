"""TRUST SHIELD: a rule based guard that inspects any draft or text before it is published.

It flags unsupported claims and statistics, absolute, health and finance claims, fake scarcity and urgency,
dark patterns, engagement bait, hidden text and prompt injection aimed at models, cloaking, fake reviews,
open placeholders, missing sponsorship disclosure, personal data, avoided terms, keyword stuffing, clickbait
and unknown citations. Patterns exist in English and Czech and are matched on a lower case, diacritics free
copy of the text, so Czech typed without diacritics is caught too. Messages follow the content language.
The shield is a heuristic reviewer, not a lawyer: every hit says what to check, none is a legal verdict.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from ..scoring import detect_lang, fold, score_hook
from . import claims as claims_profile
from .seo import CITE_RE, PLACEHOLDER_RE, _URL_RE, keyword_density, norm_lang, plain_text
from .types import Brief, Draft, Issue

MAX_PER_CODE = 5
_SEV_RANK = {"error": 0, "warn": 1, "info": 2}

# severity and bilingual message (en, cs) per code
_RULES: dict[str, tuple[str, str, str]] = {
    "UNSUPPORTED_CLAIM": ("error",
        "Evidence claim without a citation. Add a cite marker for a vetted source in the same or the next "
        "sentence, or rephrase it as your own experience.",
        "Tvrzení opírající se o důkazy bez citace. Přidejte značku citace ověřeného zdroje ve stejné nebo "
        "další větě, nebo to přeformulujte jako vlastní zkušenost."),
    "STAT_WITHOUT_SOURCE": ("warn",
        "Statistic without a source. Cite a vetted source or use a number from your own supplied facts.",
        "Statistika bez zdroje. Citujte ověřený zdroj nebo použijte číslo z vlastních dodaných faktů."),
    "ABSOLUTE_CLAIM": ("warn",
        "Absolute claim. Replace it with a specific, verifiable statement.",
        "Absolutní tvrzení. Nahraďte ho konkrétním, ověřitelným tvrzením."),
    "HEALTH_CLAIM": ("error",
        "Health or medical claim (cure, treat, detox, rapid weight loss). Remove it or have it checked by a "
        "qualified professional; advertising rules restrict these claims.",
        "Zdravotní nebo lékařské tvrzení (léčba, detox, rychlé hubnutí). Odstraňte ho nebo ho nechte posoudit "
        "odborníkem; reklamní pravidla tato tvrzení omezují."),
    "FINANCE_CLAIM": ("error",
        "Financial promise (guaranteed returns, risk-free profit, get rich). Remove it; such claims are "
        "misleading and heavily regulated.",
        "Finanční slib (zaručený výnos, zisk bez rizika, zbohatnutí). Odstraňte ho; taková tvrzení jsou "
        "klamavá a přísně regulovaná."),
    "FAKE_SCARCITY": ("error",
        "Scarcity claim that your facts do not back. Remove it or add the real stock or capacity to the brief "
        "facts.",
        "Tvrzení o nedostatku, které vaše fakta nepodporují. Odstraňte ho nebo doplňte skutečné zásoby či "
        "kapacitu do faktů zadání."),
    "FAKE_URGENCY": ("error",
        "Urgency or countdown claim that your facts do not back. Use a real deadline from the brief facts or "
        "remove it.",
        "Tvrzení o časovém tlaku nebo odpočtu, které vaše fakta nepodporují. Použijte skutečný termín z faktů "
        "zadání, nebo ho odstraňte."),
    "CONFIRMSHAMING": ("warn",
        "Confirmshaming: the decline option shames the reader. Use a neutral decline text.",
        "Confirmshaming: text volby pro odmítnutí čtenáře zahanbuje. Použijte neutrální formulaci."),
    "ENGAGEMENT_BAIT": ("warn",
        "Engagement bait (asks for likes, comments or tags for nothing in return). Platforms demote it; ask a "
        "genuine question instead.",
        "Návnada na interakci (žádá lajky, komentáře nebo označení bez protihodnoty). Platformy ji "
        "penalizují; raději položte skutečnou otázku."),
    "HIDDEN_PROMPT_INJECTION": ("error",
        "Hidden text or instructions aimed at AI models. Remove it: answer engines penalise it and it "
        "deceives readers.",
        "Skrytý text nebo pokyny určené AI modelům. Odstraňte je: vyhledávače a odpovědní systémy to "
        "penalizují a pro čtenáře je to klamavé."),
    "CLOAKING": ("error",
        "Cloaking: serving different content to bots and to people is deceptive. Show both the same content.",
        "Cloaking: jiný obsah pro roboty a pro lidi je klamavý. Ukazujte oběma stejný obsah."),
    "FAKE_REVIEW": ("error",
        "Fake or unverifiable review or rating. Use only real, attributable reviews supplied by the user.",
        "Falešná nebo neověřitelná recenze či hodnocení. Používejte jen skutečné, dohledatelné recenze dodané "
        "uživatelem."),
    "PLACEHOLDER_OPEN": ("warn",
        "{n} placeholder(s) still open ({names}). Fill or remove them before publishing.",
        "Stále zbývá otevřených zástupných textů: {n} ({names}). Vyplňte je nebo odstraňte před zveřejněním."),
    "PLACEHOLDER_NOTE": ("warn",
        "A bracketed note for the editor is still in the text ('{note}'). Fill in real information or remove it before publishing.",
        "V textu zůstala poznámka pro redaktora v hranatých závorkách ('{note}'). Doplňte skutečný údaj nebo ji před zveřejněním odstraňte."),
    "DISCLOSURE_MISSING": ("error",
        "Sponsored or affiliate content without a disclosure. Add #ad, 'sponsored', 'affiliate' or the local "
        "equivalent where readers see it first.",
        "Placený nebo affiliate obsah bez označení. Přidejte #reklama, 'reklama', 'spolupráce' nebo "
        "'affiliate' tam, kde to čtenář uvidí jako první."),
    "AI_DISCLOSURE_REMINDER": ("info",
        "AI assisted content may need labelling under platform rules and the EU AI Act transparency duties. "
        "Check the rules that apply to you; this is not legal advice.",
        "Obsah vytvořený s pomocí AI může vyžadovat označení podle pravidel platforem a povinností "
        "transparentnosti podle evropského nařízení o AI. Ověřte si pravidla, která se vás týkají; nejde o "
        "právní poradenství."),
    "PERSONAL_DATA": ("warn",
        "Personal data in the text ({kind}). Remove it unless you have a clear reason and permission to "
        "publish it.",
        "Osobní údaje v textu ({kind}). Odstraňte je, pokud nemáte jasný důvod a souhlas k jejich zveřejnění."),
    "AVOIDED_TERM": ("warn",
        "Avoided term used: '{term}'. Rephrase it.",
        "Použit nežádoucí výraz: '{term}'. Přeformulujte ho."),
    "KEYWORD_STUFFING": ("warn",
        "Keyword density {d}% is above 3%: this reads as stuffing. Use natural wording and variations.",
        "Hustota klíčového slova {d} % je nad 3 %: působí to jako přeplňování. Pište přirozeně a používejte "
        "varianty."),
    "CLICKBAIT": ("warn",
        "The hook reads as clickbait (risk {r}). Promise only what the content delivers.",
        "Úvodní věta působí jako clickbait (riziko {r}). Slibujte jen to, co obsah skutečně splní."),
    "CITATION_UNKNOWN": ("error",
        "Citation '{id}' is not one of the vetted sources and the ledger does not know it. Use a source from "
        "the brief.",
        "Citace '{id}' není mezi ověřenými zdroji a databáze studií ji nezná. Použijte zdroj ze zadání."),
}
_RULES.update(claims_profile.RULES)     # extra codes of the claims profile (active when a brief asks for it)
_KINDS = {"email": ("email address", "e-mailová adresa"), "phone": ("phone number", "telefonní číslo"),
          "birth": ("birth number", "rodné číslo"), "iban": ("IBAN", "IBAN")}

# -- text plumbing ---------------------------------------------------------------------
_TOKEN_RE = re.compile(r"[a-z0-9]+")


_SPACE_LIKE = "".join(map(chr, (0xA0, 0x2009, 0x202F)))      # no-break, thin and narrow no-break space
_APOSTROPHE = chr(0x2019)


def fold_aligned(text: str) -> str:
    """Lower case, diacritics free copy of ``text`` with exactly the same length, so indexes map 1:1."""
    out = []
    for ch in text:
        if ch in _SPACE_LIKE:
            out.append(" ")
            continue
        if ch == _APOSTROPHE:
            out.append("'")
            continue
        f = fold(ch.lower()) if ch.isalpha() else ch
        out.append(f if len(f) == 1 else ch)
    return "".join(out)


def excerpt(text: str, start: int, end: int, width: int = 80) -> str:
    """At most ``width`` characters of ``text`` around [start, end), whitespace collapsed, no cut words."""
    start, end = max(0, start), min(len(text), max(end, start))
    match = re.sub(r"\s+", " ", text[start:end]).strip()
    if len(match) >= width:
        return match[: width - 3] + "..."
    room = width - len(match)
    left = re.sub(r"\s+", " ", text[max(0, start - 80):start])
    right = re.sub(r"\s+", " ", text[end:end + 120])
    take_r = min(len(right), room - min(len(left), room // 3))
    take_l = min(len(left), room - take_r)
    before = left[len(left) - take_l:] if take_l else ""
    after = right[:take_r]
    if before and take_l < len(left) and before[0].isalnum() and left[len(left) - take_l - 1].isalnum():
        before = before.split(" ", 1)[1] if " " in before else ""
    if after and take_r < len(right) and after[-1].isalnum() and right[take_r].isalnum():
        after = after.rsplit(" ", 1)[0] if " " in after else ""
    return (before + match + after).strip()[:width]


_SENT_BOUNDARY = re.compile(r"(?<=[.!?…])[\"')\]]*\s+|\n+")


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for m in _SENT_BOUNDARY.finditer(text):
        if text[start:m.start()].strip():
            spans.append((start, m.start()))
        start = m.end()
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans


def _stem(word: str) -> str:
    return word[:5]


@dataclass
class _Ctx:
    text: str
    low: str                                   # folded copy, same length as text
    lang: str
    brief: Brief | None
    draft: Draft | None
    ledger: Any
    spans: list[tuple[int, int]]
    fact_tokens: list[set[str]]
    sponsored: bool
    known_ids: set[str]
    extra: str = ""                            # machine readable parts (JSON-LD) scanned for hidden instructions
    claimed: list[tuple[int, int]] = field(default_factory=list)
    exempt: list[tuple[int, int]] = field(default_factory=list)   # text the profile rules must not judge (approved footers)
    profile: Any = None                        # compiled claims profile, None for the general profile

    def issue(self, code: str, start: int, end: int, text: str | None = None, **fmt: Any) -> Issue:
        sev, en, cs = _RULES[code]
        msg = (cs if self.lang == "cs" else en).format(**fmt) if fmt else (cs if self.lang == "cs" else en)
        src = self.text if text is None else text
        return Issue(sev, code, msg, excerpt(src, start, end))

    def sent_of(self, pos: int) -> int:
        for i, (a, b) in enumerate(self.spans):
            if a <= pos < b or pos < a:
                return i
        return max(0, len(self.spans) - 1)

    def cited_near(self, pos: int) -> bool:
        """A cite marker, link or numeric reference in the sentence of ``pos`` or the next one."""
        i = self.sent_of(pos)
        for a, b in self.spans[i:i + 2]:
            seg = self.text[a:b]
            if CITE_RE.search(seg) or _URL_RE.search(seg) or re.search(r"\[\d+\]", seg):
                return True
        return False

    def backed(self, snippet: str) -> bool:
        """The brief facts or vetted source claims contain the numbers and most words of ``snippet``."""
        toks = set(_TOKEN_RE.findall(snippet))
        digits = {t for t in toks if t.isdigit()}
        words = {_stem(t) for t in toks if t.isalpha() and len(t) >= 3}
        if not digits and not words:
            return False
        for ftoks in self.fact_tokens:
            if digits and not digits <= ftoks:
                continue
            fwords = {_stem(t) for t in ftoks if t.isalpha()}
            if words and len(words & fwords) / len(words) < 0.5:
                continue
            return True
        return False

    def overlaps(self, start: int, end: int) -> bool:
        return any(a < end and start < b for a, b in self.claimed)

    def disclaimed(self, start: int, end: int) -> bool:
        """With a claims profile: the text is a negated statement ("does not treat disease") or an approved footer."""
        if self.profile is None:
            return False
        if any(a < end and start < b for a, b in self.exempt):
            return True
        return self.profile.negated(self.low, start, end, self.spans)


def _compile(patterns: Iterable[str]) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{p})" for p in patterns))


# -- pattern tables (matched on the folded text, so Czech is written without diacritics) -------
_CLAIM_RE = _compile([
    r"\bstudies (?:show|have shown|prove|proved|confirm|suggest|found|indicate)\b",
    r"\bresearch (?:shows|proves|has shown|has proven|confirms|suggests|found|indicates)\b",
    r"\bscience (?:says|shows|proves|confirms)\b",
    r"\bscientifically (?:proven|proved|tested|backed|validated|verified)\b",
    r"\bclinically (?:proven|tested|shown)\b",
    r"\b(?:experts|scientists|researchers|doctors|dentists) (?:agree|say|recommend|confirm|found)\b",
    r"\baccording to (?:studies|research|experts|scientists|science|surveys)\b",
    r"\b(?:a|one|recent|new|latest|another|the) (?:study|survey|report|analysis|trial) (?:shows|showed|found|says|revealed|proves|proved|confirms)\b",
    r"\bit(?:'s| is) (?:been )?(?:proven|proved) that\b",
    r"\bproven to (?:work|boost|improve|increase|reduce|help)\b",
    r"\bstudie (?:ukazuj\w*|ukazal\w*|prokazuj\w*|prokazal\w*|potvrzuj\w*|potvrdil\w*|dokazuj\w*|dokazal\w*|zjistil\w*)\b",
    r"\bpodle (?:studii|vyzkumu|vyzkumniku|vedcu|odborniku|expertu|pruzkumu|statistik)\b",
    r"\bvyzkum(?:y)? (?:ukazuj\w*|ukazal\w*|prokazal\w*|prokazuj\w*|potvrzuj\w*|potvrdil\w*|dokazal\w*|dokazuj\w*|zjistil\w*)\b",
    r"\bvedecky (?:prokazan\w*|dokazan\w*|overen\w*|podlozen\w*|testovan\w*)\b",
    r"\bklinicky (?:prokazan\w*|testovan\w*|overen\w*)\b",
    r"\b(?:odbornici|experti|vedci|lekari|zubari) (?:se shoduji|doporucuji|tvrdi|potvrzuji|zjistili|prokazali)\b",
    r"\bje (?:to )?(?:vedecky )?(?:prokazano|dokazano)\b", r"\b(?:prokazano|dokazano) je\b", r"\bbylo (?:vedecky )?(?:prokazano|dokazano)\b",
    r"\b(?:nova|nedavna|jedna|posledni) (?:studie|analyza|pruzkum|zprava) (?:ukazuje|ukazala|zjistila|prokazala|potvrdila)\b",
])
_PERCENT_RE = re.compile(r"(?<![\w.])\d{1,3}(?:[.,]\d+)?\s?(?:%|percent\b|per cent\b|procent\w*)")
_OUTOF_RE = re.compile(r"(?<![\w.])\d{1,3}\s+(?:out of|in every|of every)\s+\d{1,3}\b|(?<![\w.])\d{1,3}\s+z\s+\d{1,3}\b")
_OFFER_CONTEXT_RE = re.compile(r"\b(?:off|discount|save|saving|sleva|slevu|slevy|slevou|usetrite|usetri|zlevn\w*|akce)\b")
_ABSOLUTE_RE = _compile([
    r"\bguaranteed\b", r"\bguarantees? (?:results|success|that|you|to)\b", r"\b100\s?(?:%|percent|per cent)",
    r"\balways works?\b", r"\bnever fails?\b", r"\bworks every time\b", r"\bno risk\b", r"\brisk[- ]free\b", r"\bfoolproof\b",
    r"\bperfect results?\b", r"\bbest in the world\b", r"\bcompletely safe\b", r"\bzero (?:risk|side effects)\b",
    r"\b(?:instant|overnight) results?\b", r"\bwithout (?:any )?(?:effort|risk)\b", r"\bno effort\b",
    r"\bzarucen\w*", r"\bgarantuj\w*", r"\bgarantovan\w*", r"\b100\s?(?:%|procent\w*)", r"\bstoprocentn\w*", r"\bfunguje vzdy\b",
    r"\bnikdy nezklam\w*", r"\bbez rizika\b", r"\bbez namahy\b", r"\bbez usili\b", r"\bzadne riziko\b", r"\bnejlepsi na svete\b",
    r"\bdokonal\w+ vysledk\w*", r"\bokamzit\w+ vysledk\w*",
])
_HEALTH_RE = _compile([
    r"\bcures?\b", r"\bcuring\b", r"\bmiracle (?:cure|pill|remedy|supplement)\b",
    r"\btreats?\s+(?:cancer|diabetes|depression|anxiety|arthritis|alzheimer\w*|disease|illness|infection|insomnia|migraines?|acne)\b",
    r"\bprevents?\s+(?:cancer|disease|diabetes|covid\w*|infections?|heart disease|alzheimer\w*)\b", r"\bdetox\w*",
    r"\bcleanses? (?:your )?(?:body|liver|colon)\b", r"\b(?:boosts?|strengthens?) (?:your )?immune system\b",
    r"\breverse[sd]?\s+(?:aging|diabetes|hair loss)\b",
    r"\blos(?:e|es|ing)\s+(?:up to\s+)?\d+\s*(?:kg|kilos?|kilograms?|lbs?|pounds?)\b[^.\n]{0,40}\bin\s+(?:just\s+|only\s+)?\d+\s+(?:days?|weeks?)\b",
    r"\bvylec\w*", r"\bleci\b", r"\blecivy\w*", r"\bzazracn\w+ (?:ucink\w*|lek\w*|prostredek\w*|kur\w*)\b", r"\bodtravnen\w*",
    r"\b(?:posil\w+|zvys\w+) imunit\w*", r"\bzbav\w+ (?:vas |se )?(?:bolest\w*|alergi\w*|nemoc\w*|cukrovk\w*)\b",
    r"\bzabran\w+ (?:rakovin\w*|nemoc\w*|cukrovk\w*|infekc\w*)\b",
    r"\b(?:zhubn\w+|shod\w+|hubn\w+)\s+(?:az\s+)?(?:o\s+)?\d+\s*(?:kg|kilo\w*)\b[^.\n]{0,40}\bza\s+\d+\s+(?:dn\w*|tyd\w*|hodin\w*)\b",
])
_FINANCE_RE = _compile([
    r"\bguaranteed (?:returns?|profits?|income|gains?|earnings)\b", r"\brisk[- ]free (?:profit|profits|returns?|investment|income|trading)\b",
    r"\bno[- ]risk (?:profit|investment|returns?|trading)\b", r"\bget[- ]rich(?:[- ]quick)?\b", r"\bdouble your (?:money|investment|income)\b",
    r"\bguaranteed to (?:make|earn|profit|grow|double)\b", r"\bfinancial freedom in\b",
    r"\b(?:earn|make)\s+\$?\d[\d,. ]*(?:k|usd|eur|czk|dollars?|euros?)?\s+(?:a|per)\s+(?:day|week|month)\b",
    r"\b(?:zarucen|garantovan)\w* (?:vynos\w*|zisk\w*|prijm\w*)\b", r"\bzisk bez rizika\b", r"\bbez rizika (?:zisk\w*|vynos\w*|investic\w*)\b",
    r"\bzbohatn\w+", r"\bzbohat\w* (?:rychle|za)\b", r"\bzdvojnasob\w* (?:svoj\w+ |sve )?(?:penize|investic\w*|prijm\w*)\b",
    r"\bfinancni svobod\w+ (?:za|behem)\b", r"\bvydelej\w*\s+\d[\d ]*\s*(?:kc|czk|eur)\b",
])
_SCARCITY_RE = _compile([
    r"\bonly\s+\d+\s+(?:left|remaining|available|in stock|spots?|seats?|places?|pieces?|units?|items?|pairs?)\b",
    r"\b(?:just|only)\s+(?:a few|a handful of|\d+)\s+(?:items?|pieces?|units?|spots?|seats?|places?|pairs?)\s+(?:left|remaining|available)\b",
    r"\blimited (?:stock|supply|quantities|availability|spots|seats|places)\b", r"\bwhile (?:stocks?|supplies) last\b",
    r"\bselling fast\b", r"\balmost sold out\b", r"\b(?:nearly|almost) gone\b",
    r"\blast (?:few|\d+) (?:items?|pieces?|units?|spots?|seats?|pairs?)\b",
    r"\b\d+\s+(?:items?|pieces?|units?|spots?|seats?|pairs?)\s+(?:left|remaining)\b",
    r"\bzbyvaj\w*\s+(?:uz\s+)?(?:jen\s+|pouze\s+)?\d+\b", r"\bzbyva\s+(?:uz\s+)?(?:jen\s+|pouze\s+)?\d+\b",
    r"\b(?:uz\s+)?(?:jen|pouze)\s+\d+\s+(?:kus\w*|mist\w*|volnych|zbyva\w*)\b", r"\bposledni\s+(?:\d+\s+)?(?:kus\w*|mist\w*)\b",
    r"\bomezene (?:mnozstvi|zasoby|pocet|kapacita)\b", r"\bdo vyprodani zasob\b", r"\bskoro vyprodan\w*", r"\brychle se vyprodava\b",
])
_URGENCY_RE = _compile([
    r"\b(?:offer|sale|deal|discount|promotion|promo)\s+ends?\s+(?:in\s+(?!\d)|today|tonight|soon|at midnight|tomorrow)\b",
    r"\bends?\s+in\s+\d+\s+(?:minutes?|mins?|hours?|seconds?|secs?)\b", r"\b(?:hurry|act now|act fast|act today)\b",
    r"\blast chance\b", r"\btoday only\b", r"\blimited[- ]time (?:only|offer|deal)\b", r"\bexpires? (?:today|tonight|soon|in \d+)\b",
    r"\b\d+\s+(?:minutes?|hours?)\s+(?:left|remaining)\b", r"\bcountdown\b", r"\bclock is ticking\b",
    r"\bbefore it(?:'s| is) too late\b", r"\bnow or never\b", r"\boffer expires\b",
    r"\b(?:akce|nabidka|sleva|prodej)\s+konci\s+(?:za|dnes|v pulnoci|uz|zitra|brzy)\b",
    r"\bkonci\s+za\s+\d+\s*(?:minut\w*|hodin\w*|sekund\w*|dn\w*)\b",
    r"\bposledni sance\b", r"\bspejte\b", r"\bspechejte\b", r"\bsputejte\b", r"\bjen dnes\b", r"\bpouze dnes\b", r"\bcas vyprsi\b",
    r"\bzbyva\s+(?:uz\s+)?(?:jen\s+)?\d+\s+(?:minut\w*|hodin\w*|dn\w*)\b", r"\bodpocet\b", r"\bnabidka (?:brzy )?(?:vyprsi|zmizi)\b",
    r"\bpredtim nez bude pozde\b", r"\bted nebo nikdy\b", r"\bomezeny cas\b", r"\bcasove omezen\w*",
])
_SHAMING_RE = _compile([
    r"\bno,? thanks?,? i (?:don'?t|do not|hate|prefer|like|would rather|already|am not|'m not|enjoy)\b",
    r"\bno,? i (?:don'?t|do not) (?:want|like|care|need)\b[^.\n]{0,40}\b(?:saving|save|money|growth|success|results|improv\w*|discount\w*|deals?)\b",
    r"\bi(?:'d| would) rather (?:pay|stay|lose|miss|fail|waste|keep losing|be)\b",
    r"\bi (?:don'?t|do not) (?:like|want|care about) (?:saving|to save|money|growth|success|winning|being successful)\b",
    r"\bno,? i(?:'ll| will) (?:pay|stay|miss|lose)\b", r"\bi (?:hate|prefer) (?:saving|paying more|losing|failing|being broke)\b",
    r"\bno,? i (?:enjoy|prefer) (?:paying|losing|wasting|missing)\b",
    r"\bne,? dekuji,? (?:ja )?(?:nechci|radsi|nemam rad|nezajima|nepotrebuji|nema smysl)\b",
    r"\bne,? (?:nechci|nezajima me) (?:usetrit|vydelat|uspech|rust|slevu)\b", r"\bradsi (?:zaplatim vic|prijdu o|zustanu|budu platit)\b",
    r"\bnechci (?:usetrit|byt uspesn\w+|rust|vic penez|slevu)\b",
])
_BAIT_RE = _compile([
    r"\bcomment\s+[\"']?(?:yes|me|interested|info|guide|link|ready|want|ebook|send|1)\b",
    r"\btag (?:a|your|two|three|\d+|someone)\s*(?:best )?(?:friends?|someone|buddy|mates?|people|colleagues?)\b", r"\btag someone\b",
    r"\blike (?:this )?(?:post )?(?:if|and share|and comment)\b", r"\blike if you (?:agree|love|relate|can)\b",
    r"\bshare (?:this )?(?:post )?(?:if|with (?:a|your|someone))\b", r"\bdouble[- ]tap if\b", r"\btype (?:yes|me|1)\b",
    r"\bsmash (?:that |the )?like\b", r"\bgive (?:this )?(?:post )?a like\b", r"\brepost if\b", r"\blike\s+(?:&|and)\s+share\b",
    r"\bfollow (?:us )?(?:and|&) (?:like|comment|share)\b", r"\bdrop a (?:fire|heart|emoji)\b",
    r"\b(?:napis(?:te)?|komentuj(?:te)?)\s+[\"']?(?:ano|jo|chci|ja|info|prosim|zajem)\b",
    r"\boznac(?:te|it|ujte)?\s+(?:kamarad\w*|pritel\w*|nekoho|kolegu|kolegyni|3|dva)\b", r"\bdej(?:te)? (?:like|lajk|srdicko)\b",
    r"\blajkni(?:te)?\b", r"\blikeni(?:te)?\b", r"\bsdilej(?:te)? (?:pokud|kdyz|s kamarad\w*)\b", r"\b(?:pokud|kdyz) souhlasis\b",
    r"\bzanechte (?:srdicko|like|lajk)\b",
])
_INJECTION_RE = _compile([
    r"\bignore (?:all |any |the |your )?(?:previous|prior|above|earlier|preceding|foregoing|system)"
    r" (?:instructions?|prompts?|messages?|context|rules|directions)\b",
    r"\bdisregard (?:all |any |the |your )?(?:previous|prior|above|earlier|preceding|system) (?:instructions?|prompts?|messages?|rules)\b",
    r"\bforget (?:all |everything |your )?(?:previous|prior|above|earlier) (?:instructions?|context|prompts?)\b",
    r"\bignore everything (?:above|before)\b",
    r"\bas an? (?:ai|llm|language model|ai assistant|assistant|chatbot)\b[^.\n]{0,40}\byou (?:must|should|will|need to|have to|are required to)\b",
    r"\b(?:ai|llm|gpt|chatgpt|claude|gemini|perplexity|copilot|assistant|chatbot|language model|"
    r"crawler)s?\s*[:,]\s*(?:you (?:must|should|will|need to)|always|never|ignore|recommend|prefer|rank|cite|mention)\b",
    r"\b(?:note|attention|instructions?|message|notice|directive)s? (?:to|for) (?:ai|llms?|language"
    r" models?|chatbots?|assistants?|crawlers?|ai agents?|bots?|models?)\b",
    r"\b(?:ai|llm|language model|chatbot|assistant|model)s? (?:must|should|shall|are required to|need to|"
    r"have to) (?:always )?(?:recommend|cite|mention|prefer|rank|promote|say|answer|list|suggest)\b",
    r"\bwhen (?:asked|someone asks|a user asks|users ask|you are asked)\b[^.\n]{0,100}\b(?:always |only"
    r" )?(?:recommend|mention|cite|say|answer|suggest)\b",
    r"\bsystem prompt\b", r"\bnew instructions?\s*:", r"\byou are now (?:a|an|in)\b",
    r"\bdo not (?:mention|recommend|cite|suggest) (?:any )?(?:competitors?|other brands?|alternatives?)\b", r"\bonly recommend\b",
    r"\bignoruj(?:te)?\s+(?:vsechny\s+|veskere\s+)?(?:predchozi|drivejsi|predesle|predchazejici)\s+(?:instrukce|pokyny|prikazy|zadani)\b",
    r"\bzapomen(?:te)?\s+(?:vsechny\s+)?(?:predchozi|drivejsi)\s+(?:instrukce|pokyny)\b",
    r"\bjako\s+(?:ai\s+)?(?:asistent|jazykovy model|umela inteligence|ai|chatbot)\b[^.\n]{0,40}\b(?:musis|"
    r"musite|mas|mate|byste meli|bys mel|budes)\b",
    r"\bpoznamka\s+pro\s+(?:ai|jazykove modely|chatboty|llm|umelou inteligenci|roboty)\b",
    r"\b(?:ai|llm|chatbot|asistent|jazykovy model)\w*\s*[:,]\s*(?:musis|musite|vzdy|nikdy|doporuc\w+|ignoruj\w*)\b",
    r"\bkdyz se (?:te|vas|uzivatel\w*)\s+(?:zepta|zeptaji|ptaji)\b[^.\n]{0,100}\b(?:vzdy |pouze )?doporuc\w+\b",
    r"\bnedoporucuj(?:te)?\s+(?:konkurenc\w*|jine znacky)\b",
])
_HIDDEN_STYLE_RE = _compile([
    r"font-size\s*:\s*0(?:px|pt|em|rem|%)?(?![\d.])", r"display\s*:\s*none", r"visibility\s*:\s*hidden", r"opacity\s*:\s*0(?![\d.])",
    r"text-indent\s*:\s*-\s*\d{3,}", r"(?:left|top)\s*:\s*-\s*\d{3,}px", r"height\s*:\s*0(?:px)?\s*;[^\"'>]{0,40}overflow\s*:\s*hidden",
    r"(?<![-\w])color\s*:\s*transparent",
    r"<!--[^>]{0,300}\b(?:ignore|instructions?|llm|assistant|recommend)\b[^>]{0,300}-->",
])
_WHITE = r"(?:#fff(?:fff)?\b|white\b|rgb\(\s*255\s*,\s*255\s*,\s*255\s*\))"
_WHITE_ON_WHITE_RE = re.compile(
    rf"(?<![-\w])color\s*:\s*{_WHITE}[^\"'>]{{0,120}}background(?:-color)?\s*:\s*{_WHITE}|"
    rf"background(?:-color)?\s*:\s*{_WHITE}[^\"'>]{{0,120}}(?<![-\w])color\s*:\s*{_WHITE}")
_INVISIBLE_RE = re.compile("[" + "".join(map(chr, (0x200B, 0x200C, 0x2060, 0x180E, 0xFEFF))) + "]")
_TAG_CHARS_RE = re.compile("[\U000e0000-\U000e007f]")
_CLOAK_RE = _compile([
    r"\b(?:serve|show|display|deliver|present)s?\s+(?:different|separate|alternate|other)\s+(?:content|"
    r"text|pages?|versions?)\s+(?:to|for)\s+(?:bots?|crawlers?|search engines?|googlebot|ai|llms?|robots?)\b",
    r"\bif\s*\(?[^)\n]{0,60}user[-_ ]?agent[^)\n]{0,60}(?:googlebot|gptbot|claudebot|bingbot|perplexitybot|ccbot|oai-searchbot)",
    r"\bjin\w+\s+(?:obsah|text|verzi)\s+(?:pro|nez pro)\s+(?:roboty|boty|vyhledavace|crawlery|ai)\b",
    r"\bpro\s+(?:roboty|boty|vyhledavace|crawlery)\s+(?:zobraz\w+|servir\w+|posil\w+)\s+jin\w+\s+(?:obsah|text|verzi)\b",
])
_FAKE_REVIEW_CMD_RE = _compile([
    r"\b(?:write|post|generate|buy|order|publish|fabricate)\s+(?:some\s+|a few\s+|\d+\s+)?(?:fake|5[- ]star|five[- ]star|positive)\s+reviews?\b",
    r"\b(?:naps\w+|napis\w+|koupit|objednat|vygenerovat)\s+(?:si\s+)?(?:falesn\w+|placen\w+|petihvezdick\w+)\s+recenz\w+\b",
])
_REVIEW_LIKE_RE = _compile([
    "[" + chr(0x2605) + chr(0x2B50) + "]{3,}", r"\b(?:verified|overeny|overeni)\s+(?:buyer|purchase|customer|purchaser|zakaznik|nakup|kupujici)\b",
    r"\b[45](?:[.,][0-9])?\s*(?:/|out of|z)\s*5\s*(?:stars?|hvezd\w*)\b", r"\b(?:five|5)[- ]star (?:review|rating)s?\b",
])
_SPONSOR_RE = _compile([
    r"(?<![a-z0-9])#ad\b", r"#reklama", r"#sponsored", r"#spon\b", r"\bsponsored\b", r"\bsponzorov\w*", r"\breklama\b", r"\breklamni\b",
    r"\bspoluprace\b", r"\baffiliate\b", r"\bpartnersk\w+ odkaz\w*", r"\bpaid partnership\b", r"\badvertisement\b",
    r"\bpaid promotion\b", r"\bin collaboration with\b",
])
_ROLE_MAILBOXES = {
    "info", "hello", "hi", "contact", "press", "media", "pr", "support", "help", "sales", "office", "team", "admin", "marketing",
    "newsletter", "noreply", "no-reply", "careers", "jobs", "billing", "service", "kontakt", "podpora", "obchod", "redakce", "tisk",
}


# -- personal data validators ----------------------------------------------------------
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_PHONE_RES = (
    re.compile(r"(?<![\w/.,-])(?:\+|00)\d{1,3}[ .-]?\(?\d{1,4}\)?(?:[ .-]?\d{2,4}){2,4}(?!\w)"),
    re.compile(r"(?<![\w/.,+-])\d{3}[ .-]\d{3}[ .-]\d{3}(?!\d)(?!\s?(?i:kč|kc|czk|eur|usd|€|\$))"),
    re.compile(r"(?<![\w/.,+-])\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)"),
)
_RC_SLASH_RE = re.compile(r"(?<![\d/])(\d{2})(\d{2})(\d{2})/(\d{3,4})(?!\d)")
_RC_PLAIN_RE = re.compile(r"(?<![\d/.,+-])(\d{2})(\d{2})(\d{2})(\d{4})(?!\d)")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b")


def _valid_birth_number(yy: str, mm: str, dd: str, suffix: str) -> bool:
    """Czech/Slovak rodne cislo: plausible date (month +20 or +50 or +70 allowed) and, for 10 digits, divisible by 11."""
    month, day = int(mm), int(dd)
    if month > 70:
        month -= 70
    elif month > 50:
        month -= 50
    elif month > 20:
        month -= 20
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return False
    if len(suffix) == 3:
        return True
    first9 = int(yy + mm + dd + suffix[:3])
    return int(yy + mm + dd + suffix) % 11 == 0 or (first9 % 11 == 10 and suffix[-1] == "0")


def _valid_iban(raw: str) -> bool:
    s = raw.replace(" ", "")
    if not 15 <= len(s) <= 34:
        return False
    return int("".join(str(int(c, 36)) for c in s[4:] + s[:4])) % 97 == 1


def _personal_data(text: str) -> list[tuple[str, int, int]]:
    hits: list[tuple[str, int, int]] = []
    for m in _EMAIL_RE.finditer(text):
        if m.group().split("@", 1)[0].lower() not in _ROLE_MAILBOXES:
            hits.append(("email", m.start(), m.end()))
    for rx in _PHONE_RES:
        for m in rx.finditer(text):
            if 9 <= len(re.sub(r"\D", "", m.group())) <= 15:
                hits.append(("phone", m.start(), m.end()))
    for m in _RC_SLASH_RE.finditer(text):
        if _valid_birth_number(*m.groups()):
            hits.append(("birth", m.start(), m.end()))
    for m in _RC_PLAIN_RE.finditer(text):
        if _valid_birth_number(*m.groups()) and len(m.group(4)) == 4:
            hits.append(("birth", m.start(), m.end()))
    for m in _IBAN_RE.finditer(text):
        if _valid_iban(m.group()):
            hits.append(("iban", m.start(), m.end()))
    kept: list[tuple[str, int, int]] = []
    for kind, a, b in sorted(hits, key=lambda h: (h[1], -h[2])):     # drop phone hits that sit inside a longer hit
        if not any(k2 != kind and a2 <= a and b <= b2 for k2, a2, b2 in kept) and (kind, a, b) not in kept:
            kept.append((kind, a, b))
    return kept


# -- rules -----------------------------------------------------------------------------
def _r_health(ctx: _Ctx) -> list[Issue]:
    out = []
    for m in _HEALTH_RE.finditer(ctx.low):
        if ctx.overlaps(*m.span()) or ctx.disclaimed(*m.span()):    # the claims profile already judged this text
            continue
        ctx.claimed.append(m.span())
        out.append(ctx.issue("HEALTH_CLAIM", *m.span()))
    return out


def _r_finance(ctx: _Ctx) -> list[Issue]:
    out = []
    for m in _FINANCE_RE.finditer(ctx.low):
        ctx.claimed.append(m.span())
        out.append(ctx.issue("FINANCE_CLAIM", *m.span()))
    return out


def _r_absolute(ctx: _Ctx) -> list[Issue]:
    out = []
    for m in _ABSOLUTE_RE.finditer(ctx.low):
        if ctx.overlaps(*m.span()) or ctx.backed(m.group()):
            continue
        ctx.claimed.append(m.span())
        out.append(ctx.issue("ABSOLUTE_CLAIM", *m.span()))
    return out


def _r_stat(ctx: _Ctx) -> list[Issue]:
    out = []
    for rx in (_PERCENT_RE, _OUTOF_RE):
        for m in rx.finditer(ctx.low):
            if ctx.overlaps(*m.span()):
                continue
            if rx is _PERCENT_RE:
                window = ctx.low[max(0, m.start() - 16):m.end() + 16]
                if _OFFER_CONTEXT_RE.search(window) or re.match(r"100\b", m.group()):
                    continue                       # offer terms and "100 percent" (absolute claim rule) are not statistics
            if ctx.cited_near(m.start()) or ctx.backed(m.group()):
                continue
            out.append(ctx.issue("STAT_WITHOUT_SOURCE", *m.span()))
    return out


def _is_question_at(text: str, end: int) -> bool:
    """True when the first sentence terminator after ``end`` on the same line is a question mark."""
    rest = text[end:].split("\n", 1)[0]
    match = re.search(r"[.!?]", rest)
    return bool(match) and match.group() == "?"


def _r_unsupported(ctx: _Ctx) -> list[Issue]:
    # A claim phrase inside a question ("What do experts say?") is not a claim.
    return [ctx.issue("UNSUPPORTED_CLAIM", *m.span()) for m in _CLAIM_RE.finditer(ctx.low)
            if not ctx.cited_near(m.start()) and not _is_question_at(ctx.low, m.end())]


def _r_scarcity(ctx: _Ctx) -> list[Issue]:
    return [ctx.issue("FAKE_SCARCITY", *m.span()) for m in _SCARCITY_RE.finditer(ctx.low) if not ctx.backed(m.group())]


def _r_urgency(ctx: _Ctx) -> list[Issue]:
    return [ctx.issue("FAKE_URGENCY", *m.span()) for m in _URGENCY_RE.finditer(ctx.low) if not ctx.backed(m.group())]


def _r_shaming(ctx: _Ctx) -> list[Issue]:
    return [ctx.issue("CONFIRMSHAMING", *m.span()) for m in _SHAMING_RE.finditer(ctx.low)]


def _r_bait(ctx: _Ctx) -> list[Issue]:
    return [ctx.issue("ENGAGEMENT_BAIT", *m.span()) for m in _BAIT_RE.finditer(ctx.low)]


def _r_injection(ctx: _Ctx) -> list[Issue]:
    out: list[Issue] = []

    def scan(text: str) -> None:
        low = fold_aligned(text)
        for rx in (_INJECTION_RE, _HIDDEN_STYLE_RE, _WHITE_ON_WHITE_RE):
            for m in rx.finditer(low):
                out.append(ctx.issue("HIDDEN_PROMPT_INJECTION", *m.span(), text=text))
        invisible = [m for m in _INVISIBLE_RE.finditer(text) if m.start() > 0]
        if len(invisible) >= 3:
            out.append(ctx.issue("HIDDEN_PROMPT_INJECTION", invisible[0].start(), invisible[-1].end(), text=text))
        tag = _TAG_CHARS_RE.search(text)
        if tag:
            out.append(ctx.issue("HIDDEN_PROMPT_INJECTION", tag.start(), tag.end(), text=text))

    scan(ctx.text)
    if ctx.extra:
        scan(ctx.extra)
    return out


def _r_cloaking(ctx: _Ctx) -> list[Issue]:
    return [ctx.issue("CLOAKING", *m.span()) for m in _CLOAK_RE.finditer(ctx.low)]


def _r_fake_review(ctx: _Ctx) -> list[Issue]:
    out = [ctx.issue("FAKE_REVIEW", *m.span()) for m in _FAKE_REVIEW_CMD_RE.finditer(ctx.low)]
    for m in _REVIEW_LIKE_RE.finditer(ctx.low):
        a, b = ctx.spans[ctx.sent_of(m.start())] if ctx.spans else (0, len(ctx.low))
        if ctx.cited_near(m.start()) or ctx.backed(ctx.low[a:b]):
            continue
        out.append(ctx.issue("FAKE_REVIEW", *m.span()))
    return out


def _r_placeholder(ctx: _Ctx) -> list[Issue]:
    found = list(PLACEHOLDER_RE.finditer(ctx.text))
    names = list(ctx.draft.slots_open) if ctx.draft else []
    if not found and not names:
        return []
    label = ", ".join(names[:6]) + (", ..." if len(names) > 6 else "") if names else "..."
    start, end = found[0].span() if found else (0, 0)
    return [ctx.issue("PLACEHOLDER_OPEN", start, end, n=len(found) or len(names), names=label)]


# Models sometimes leave an instruction in single brackets instead of an empty slot ("[Doplňte jméno autora]").
_NOTE_RE = re.compile(
    r"(?<!\[)\[(?!\[)\s*(?:"
    r"(?:doplňte|doplň|doplnit|vložte|napište|zadejte|uveďte|upravte)\b[^\]\n]{0,200}"          # Czech imperatives are never button labels
    r"|(?:add|insert|fill in|enter|your)\b(?:(?=[^\]\n]*\bhere\b)|(?=(?:\s+[^\s\]]+){3,}\s*\]))[^\]\n]{0,200}"    # "[Add to cart]" stays alone
    r"|(?:todo|tbd|xxx)\b[^\]\n]{0,200}"
    r")\](?!\()",
    re.IGNORECASE)


def _r_placeholder_note(ctx: _Ctx) -> list[Issue]:
    out = []
    for m in _NOTE_RE.finditer(ctx.text):
        if not any(a <= m.start() < b for a, b in ctx.exempt):
            out.append(ctx.issue("PLACEHOLDER_NOTE", m.start(), m.end(), note=m.group()[1:-1].strip()[:80]))
    return out


def _r_disclosure(ctx: _Ctx) -> list[Issue]:
    if ctx.sponsored and not _SPONSOR_RE.search(ctx.low):
        return [ctx.issue("DISCLOSURE_MISSING", 0, 0)]
    return []


def _r_personal(ctx: _Ctx) -> list[Issue]:
    idx = 1 if ctx.lang == "cs" else 0
    return [ctx.issue("PERSONAL_DATA", a, b, kind=_KINDS[kind][idx]) for kind, a, b in _personal_data(ctx.text)]


def _r_avoided(ctx: _Ctx) -> list[Issue]:
    out = []
    for term in (ctx.brief.avoid if ctx.brief else []):
        t = fold_aligned(term.strip())
        if not t:
            continue
        m = re.search(r"(?<![a-z0-9])" + r"\W+".join(re.escape(w) for w in t.split()) + r"(?![a-z0-9])", ctx.low)
        if m:
            out.append(ctx.issue("AVOIDED_TERM", *m.span(), term=term.strip()))
    return out


def _r_stuffing(ctx: _Ctx) -> list[Issue]:
    kw = ((ctx.brief.primary_keyword if ctx.brief else None) or (ctx.draft.meta.get("keyword") if ctx.draft else None) or "").strip()
    if not kw:
        return []
    _, words, density = keyword_density(plain_text(ctx.text), kw, ctx.lang)
    if words < 100 or density <= 3.0 or PLACEHOLDER_RE.search(ctx.text):
        return []                                # density is only judged on complete text of a useful length
    m = re.search(re.escape(fold_aligned(kw)), ctx.low)
    a, b = m.span() if m else (0, 0)
    d = f"{density:.1f}".replace(".", ",") if ctx.lang == "cs" else f"{density:.1f}"
    return [ctx.issue("KEYWORD_STUFFING", a, b, d=d)]


def _r_clickbait(ctx: _Ctx) -> list[Issue]:
    hook = (ctx.draft.hook if ctx.draft else "") or ""
    if not hook.strip():
        hook = next((l.strip() for l in ctx.text.splitlines() if l.strip()), "")
        hook = re.sub(r"^[#>*\s-]+", "", hook)
    if not hook or PLACEHOLDER_RE.search(hook):
        return []
    try:
        risk = score_hook(hook[:300], lang=ctx.lang).clickbait_risk
    except ValueError:                                   # scoring chokes on tokens like "12.5"; retry without decimals
        risk = score_hook(re.sub(r"\d+[.,]\d+", "1", hook[:300]), lang=ctx.lang).clickbait_risk
    if risk > 0.5:
        return [ctx.issue("CLICKBAIT", 0, len(hook), text=hook, r=f"{risk:.2f}".replace(".", ",") if ctx.lang == "cs" else f"{risk:.2f}")]
    return []


def _r_citations(ctx: _Ctx) -> list[Issue]:
    out: list[Issue] = []
    seen: set[str] = set()
    for m in CITE_RE.finditer(ctx.text):
        cid = m.group(1)
        if cid in seen or cid in ctx.known_ids:
            continue
        seen.add(cid)
        if ctx.ledger is not None:
            try:
                if ctx.ledger.get_study(cid) is not None:
                    continue
            except Exception:                          # a failing ledger must not hide the problem
                pass
        out.append(ctx.issue("CITATION_UNKNOWN", m.start(), m.end(), id=cid))
    return out


_LABEL_WORDS = {"strong": ("strong", "silné"), "moderate": ("moderate", "střední"), "limited": ("limited", "omezené"),
                "contested": ("contested", "sporné"), "none": ("none", "žádné")}


def _r_claims(ctx: _Ctx) -> list[Issue]:
    """Evidence-aware claims profile (wellness): medical claims, hedging, status, safety and usage figures."""
    profile = ctx.profile
    if profile is None:
        return []
    blocked = [m.span() for m in PLACEHOLDER_RE.finditer(ctx.text)] + ctx.exempt

    def skip(a: int, b: int) -> bool:
        return any(x < b and a < y for x, y in blocked)

    out: list[Issue] = []
    hits = profile.scan(
        ctx.text, ctx.low, spans=ctx.spans, skip=skip, backed=ctx.backed, cited_near=ctx.cited_near,
        is_question=lambda end: _is_question_at(ctx.low, end), format_id=ctx.draft.format if ctx.draft else None,
    )
    for h in hits:
        fmt: dict[str, Any] = {}
        if h.topic is not None:
            words = _LABEL_WORDS.get(h.topic.label, (h.topic.label, h.topic.label))
            fmt = {"topic": h.topic.name(ctx.lang), "label": words[1] if ctx.lang == "cs" else words[0], "safe": h.topic.safe(ctx.lang)}
        if h.code == "SAFETY_NOTE_MISSING":
            sev, en, cs = _RULES[h.code]
            out.append(Issue(sev, h.code, cs if ctx.lang == "cs" else en, None))
            continue
        if h.code in ("CLAIM_MEDICAL", "CLAIM_AVOID", "DISEASE_MENTION", "STATUS_CLAIM", "SAFETY_ABSOLUTE"):
            ctx.claimed.append((h.start, h.end))
        out.append(ctx.issue(h.code, h.start, h.end, **fmt))
    return out


def _r_ai_reminder(ctx: _Ctx) -> list[Issue]:
    return [ctx.issue("AI_DISCLOSURE_REMINDER", 0, 0)]


# order matters: regulated claims first, so the softer absolute and statistic rules skip the same text
_RULE_FUNCS: tuple[Callable[[_Ctx], list[Issue]], ...] = (
    _r_claims, _r_health, _r_finance, _r_absolute, _r_stat, _r_unsupported, _r_scarcity, _r_urgency, _r_shaming, _r_bait, _r_injection,
    _r_cloaking, _r_fake_review, _r_placeholder, _r_placeholder_note, _r_disclosure, _r_personal, _r_avoided, _r_stuffing, _r_clickbait,
    _r_citations, _r_ai_reminder,
)
RULE_CODES = tuple(_RULES)


class TrustShield:
    """Rule based guard. ``ledger`` is any object with ``get_study(study_id) -> object | None``.

    The research package is never imported here; a ledger only resolves citation ids that are not in the brief.
    """

    def __init__(self, ledger: object | None = None) -> None:
        self.ledger = ledger

    def _context(self, draft_or_text: Draft | str, brief: Brief | None, lang: str | None) -> _Ctx:
        draft = draft_or_text if isinstance(draft_or_text, Draft) else None
        text = unicodedata.normalize("NFC", draft.body if draft else str(draft_or_text or ""))
        content_lang = norm_lang(lang or (draft.lang if draft else None) or (brief.lang if brief else None) or detect_lang(text))
        facts = list(brief.facts) if brief else list(draft.parts.get("facts") or []) if draft else []
        sources = list(brief.sources) if brief else list(draft.parts.get("sources") or []) if draft else []
        corpus = facts + [str(s.get(k) or "") for s in sources for k in ("claim", "title")]
        extra = ""
        if draft and draft.parts.get("json_ld"):
            extra = json.dumps(draft.parts["json_ld"], ensure_ascii=False)
        exempt: list[tuple[int, int]] = []
        for snippet in (draft.parts.get("guard_exempt") or []) if draft else []:
            snippet = str(snippet)
            at = text.find(snippet) if snippet else -1
            while at != -1:
                exempt.append((at, at + len(snippet)))
                at = text.find(snippet, at + len(snippet))
        return _Ctx(
            text=text, low=fold_aligned(text), lang=content_lang, brief=brief, draft=draft, ledger=self.ledger, exempt=exempt,
            profile=claims_profile.profile_for(brief),
            spans=_sentence_spans(text), fact_tokens=[set(_TOKEN_RE.findall(fold_aligned(c))) for c in corpus if c.strip()],
            sponsored=bool(brief.sponsored) if brief else bool(draft.meta.get("sponsored")) if draft else False,
            known_ids={str(s.get("id")) for s in sources if s.get("id")}, extra=extra,
        )

    def check(self, draft_or_text: Draft | str, brief: Brief | None = None, *, lang: str | None = None) -> list[Issue]:
        """All findings, errors first. Every issue has ``where`` with an excerpt of at most 80 characters."""
        ctx = self._context(draft_or_text, brief, lang)
        issues: list[Issue] = []
        for rule in _RULE_FUNCS:
            issues.extend(rule(ctx))
        seen: set[tuple[str, str | None, str]] = set()
        counts: dict[str, int] = {}
        dropped: dict[str, int] = {}
        kept: list[Issue] = []
        for issue in issues:
            key = (issue.code, issue.where, issue.message)
            if key in seen:
                continue
            seen.add(key)
            counts[issue.code] = counts.get(issue.code, 0) + 1
            if counts[issue.code] > MAX_PER_CODE:
                dropped[issue.code] = dropped.get(issue.code, 0) + 1
                continue
            kept.append(issue)
        for code, n in dropped.items():
            last = max(i for i, issue in enumerate(kept) if issue.code == code)
            kept[last].message += f" (+{n} dalších)" if ctx.lang == "cs" else f" (+{n} more)"
        return sorted(kept, key=lambda i: _SEV_RANK[i.severity])

    def verdict(self, issues: list[Issue]) -> str:
        """"blocked" if any error, "review" if any warning, else "ok"."""
        if any(i.severity == "error" for i in issues):
            return "blocked"
        if any(i.severity == "warn" for i in issues):
            return "review"
        return "ok"
