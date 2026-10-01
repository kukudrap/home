"""Write web/tests/golden.json: Python scorer outputs the JavaScript port must reproduce exactly.

Run from the project root:  PYTHONPATH=src python3 scripts/gen_golden.py
"""
from __future__ import annotations

import json
from pathlib import Path

from dopamine_king.scoring import score_hook
from dopamine_king.synth import generate_corpus

ROOT = Path(__file__).resolve().parent.parent

HAND_WRITTEN = [
    "", "   ", "Win", "42", "2026", "10", "1,000 users", "3.5 hours a week", "Best CRM tools 2026",
    "Save 12.5 percent on shoes", "1.25 liters a day", "12,5 procenta ro\u010dn\u011b", "2026.5 forecast", "1900.0 hours", "12.5 tips for runners",
    "Our Q3 company update", "Introducing the new Aero 2 running shoe",
    "7 mistakes every beginner runner makes (and how to fix them)",
    "You won't BELIEVE this one trick!!!", "You won’t believe this one trick!!!",
    "Why most marketing dashboards lie to you", "How to write a LinkedIn hook in 5 minutes",
    "The complete guide to email marketing automation for B2B SaaS companies in 2026 with examples and templates",
    "Stop posting every day: what 1,000 brand accounts taught us",
    "Guaranteed 10x growth overnight with this secret formula", "Is your CRM costing you deals?",
    "What nobody tells you about churn...", "SHOCKING!!! THIS CHANGES EVERYTHING!!!",
    "Jak získat prvních 100 zákazníků bez reklamy",
    "7 chyb, které dělá každý začátečník v běhu (a jak se jim vyhnout)",
    "7 chyb, ktere dela kazdy zacatecnik v behu (a jak se jim vyhnout)",
    "Naše novinky za třetí čtvrtletí", "Nevěříte, co se stalo potom!!! Šokující trik",
    "Proč většina firemních newsletterů selhává?", "Jak napsat hook na LinkedIn za 5 minut",
    "Jak zacit s marketingem bez rozpoctu", "Zaručený růst přes noc bez rizika",
    "Žluťoučký kůň úpěl ďábelské ódy", "\U0001f525 5 tips for better sleep \U0001f525",
    "Café résumé naïve façade", "é combining accent test",
    "a b c d e f g h i j k l m n o p q r s t u v w x y z a b c d e f g h i j k l m n o p q r s t u v w x y z",
    " ".join(["why most dashboards lie to you"] * 90),
]
WITH_BODY = [
    ("7 ways to cut churn", "1. one\n2. two\n3. three"),
    ("7 ways to cut churn", "\n".join(f"{i}. item {i}" for i in range(1, 8))),
    ("10 tips for better sleep", "## Tip one\ntext\n## Tip two\ntext"),
    ("1,000 ways to win", "- a\n- b"),
]
WEIGHTS = [
    {"curiosity": 1, "surprise": 0, "emotion": 0, "relevance": 0, "utility": 0},
    {"curiosity": 0.1, "surprise": 0.1, "emotion": 0.1, "relevance": 0.1, "utility": 0.6},
]


def case(text: str, body: str = "", lang: str | None = None, weights: dict | None = None) -> dict:
    result = score_hook(text, body, lang=lang, weights=weights)
    return {"text": text, "body": body, "lang": lang, "weights": weights, "expected": result.to_dict(ndigits=None)}


def main() -> None:
    cases = [case(t) for t in HAND_WRITTEN]
    cases += [case(t, b) for t, b in WITH_BODY]
    cases += [case("Why most marketing dashboards lie to you", weights=w) for w in WEIGHTS]
    cases += [case("Why most marketing dashboards lie to you", lang="cs"), case("Proč většina dashboardů liže", lang="en")]
    _, items = generate_corpus()
    cases += [case(i.title, lang=i.lang) for i in items[::17][:60]]
    out = ROOT / "web" / "tests" / "golden.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cases, ensure_ascii=False, indent=1), "utf-8")
    print(f"wrote {len(cases)} cases to {out}")


if __name__ == "__main__":
    main()
