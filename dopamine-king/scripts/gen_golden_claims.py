"""Write web/tests/claims.golden.json: claims profile results the JavaScript port must reproduce exactly.

Run from the project root:  PYTHONPATH=src python3 scripts/gen_golden_claims.py
The file holds the rules the game receives (``bundle.claim_rules``) and, per phrase, the hits of
``ClaimsProfile.scan_text`` as (code, topic, start, end).
"""
from __future__ import annotations

import json
from pathlib import Path

from dopamine_king.generate import claims
from dopamine_king.verticals import load_vertical

ROOT = Path(__file__).resolve().parent.parent

CS = [
    "Červené světlo léčí bolest kloubů.", "Panel zmírňuje zánět a bolest zad.", "Vyléčí depresi i úzkost.", "Zvyšuje testosteron a plodnost.",
    "Detoxikuje tělo a posiluje imunitu.", "Panel je zdravotnický prostředek schválený FDA.", "Bez vedlejších účinků, bezpečné pro každého.",
    "Za 4 týdny uvidíte výrazně méně vrásek.", "Podporuje růst vlasů.", "Červené světlo pomáhá při artritidě.", "Světlo na bolest zad.",
    "Zlepšuje spánek a regeneraci svalů.", "Aktivuje mitochondrie a zvyšuje produkci ATP.", "Terapie červeným světlem", "Panel proti migréně",
    "Zmírňuje depresi", "Urychluje hojení ran.", "Zlepšuje zrak u seniorů.", "Pomáhá při nespavosti.", "Snižuje obvod pasu a odstraňuje celulitidu.",
    "Mnoho lidí zařazuje sezení pod červeným světlem do večerní rutiny.",
    "Některé studie naznačují, že červené světlo před cvičením může podpořit sportovní výkon u zdravých lidí.",
    "Podle návodu výrobce se panel používá z doporučené vzdálenosti.",
    "Fotobiomodulace je název pro působení červeného a blízkého infračerveného světla na buňky.",
    "Přístroj neslouží k léčbě nemocí a nenahrazuje lékařskou péči.", "Přístroj není zdravotnický prostředek.",
    "Jak vybrat panel: vlnové délky, výkon a velikost plochy", "Může červené světlo podpořit regeneraci po tréninku?",
    "Léčí červené světlo bolest zad?", "Panel má 408 LED diod a šest vlnových délek.", "5 chyb při výběru červeného světla",
    "Mýty o červeném světle: co je pravda?", "Nebojte se. Červené světlo léčí bolest kloubů.", "Přístroj nelze použít jako léčbu bolesti.",
    "Lékařsky doporučeno a v nemocniční kvalitě.", "Naprosto bezpečné a bez rizika.", "Do dvou týdnů pocítíte rozdíl, výsledky za 14 dní.",
    "Posiluje energii a pohodu.", "Zlepšuje vzhled pleti a zpevňuje obličej.", "Pomáhá při úzkosti i při bolesti hlavy.",
    "Cervene svetlo leci bolest kloubu.", "Pomaha pri artritide a zmirnuje zanet.", "Bez vedlejsich ucinku a bez rizika.",
    "Za tri tydny uvidite rozdil, vysledky za 21 dni.", "Doporučeno lékaři, klinická kvalita.", "Červené světlo na vypadávání vlasů.",
    "Zlepšuje paměť a chrání před Alzheimerovou chorobou.", "Pomůže vám usnout a zlepší kvalitu spánku.", "Jak funguje fotobiomodulace v buňkách?",
    "Pro lidi s artritidou: panel pro každodenní použití.", "Panel pomáhá sportovcům s regenerací.", "Podporuje vaši regeneraci po každém tréninku!",
    "Stačí 10 minut denně a bolest zmizí.", "Světelná rutina před spaním může podpořit pohodu.", "",
]
EN = [
    "Red light cures joint pain.", "It relieves inflammation and back pain.", "Treats depression and anxiety.", "Boosts testosterone.",
    "FDA approved medical device.", "No side effects, safe for everyone.", "You will see fewer wrinkles in 4 weeks.", "Red light for hair loss.",
    "Supports muscle recovery and sleep quality.", "Boosts mitochondria and ATP production.", "Sessions last 10 minutes at 15 cm.", "Red light therapy",
    "Speeds up wound healing.", "Improves eyesight in older adults.", "Helps with insomnia.", "A panel for arthritis.", "Reduces swelling.",
    "Detoxifies your body and boosts immunity.", "Lose inches from your waist and melt cellulite.", "Improves skin tone and reduces wrinkles.",
    "Many people add a red light session to an evening routine.", "How to choose a panel: wavelengths, power and size.",
    "Can red light support recovery after training?", "Read the manufacturer's instructions and protect your eyes.",
    "The panel has 408 LEDs and six wavelengths.", "The device does not treat disease and does not replace medical care.",
    "This is not a medical device and it cannot cure pain.", "It is not FDA approved and makes no medical claims.",
    "Some studies suggest red light may support muscle recovery after exercise in healthy adults.",
    "Red light may support recovery, according to some studies.", "It is simple. Red light cures joint pain.", "Stop overcomplicating recovery routines",
    "Does red light cure pain?", "Completely safe and risk-free.", "Doctor recommended, medical grade.", "Results in 14 days.",
    "In just 2 weeks you will notice a difference.", "Treats and prevents infections.", "Improves memory and helps with brain fog.",
    "Red light for sleep, energy and well-being.", "Boosts your energy every day.", "Light panels for athletes with knee pain.",
    "Hair growth and hair regrowth in 3 months.", "Anti-aging glow with fine lines gone.", "Supports your recovery.", "5 mistakes people make with red light panels",
    "Is red light therapy the same as a tanning bed?", "A harmless way to relax.", "No risk, no contraindications.",
    "Mitochondria are cell structures that make energy.", "Reduce stress and calm your mind.", "A calm evening light routine.", "",
]
MIXED = [
    "Red light léčí bolest kloubů", "Detox & imunita: červené světlo", "Zlepšuje spánek (may support sleep).", "ČERVENÉ SVĚTLO LÉČÍ BOLEST!!!",
    "Světlo pro regeneraci. Světlo proti bolesti. Světlo na zánět.", "Red light. Léčba. Vyléčí.", "Ne, nelze to použít jako léčbu depresí.",
    "[[ADD: Explain how red light cures pain]]", "Léčí  bolest   zad", "léčí\nbolest", "Uleví od bolesti? Ne.", "Zmírňuje bolest, ale jen u zdravých? Možná.",
    "Pomáhá při bolesti, pomáhá při artritidě, pomáhá při migréně.", "Naprosto bezpečné. Zcela bezpečné. 100 % bezpečné.",
    # rules added after the regulation review: medication advice, targeting, masking, clause breaks, testimonials
    "Replace your painkillers with red light.", "Say goodbye to your doctor.", "Do you suffer from migraines? Try our panel.",
    "For people with diabetes: a new panel.", "This device is not intended to diagnose, treat, cure, or prevent any disease.",
    "Risk-free trial for 60 days.", "People with epilepsy should ask a doctor first.", "You do not need eye protection, it is completely harmless.",
    "My arthritis vanished in a month.", "Stop taking your medication and use red light instead.", "100% safe checkout and safe payment.",
    "Nahraďte léky světlem a přestaňte užívat léky.", "Trpíte artritidou? Vyzkoušejte panel.", "Pro lidi s cukrovkou: nový panel.",
    "Přístroj neslouží k diagnostice, léčbě ani prevenci nemocí.", "Vyzkoušejte bez rizika, bezpečná platba.", "Jste-li těhotná, poraďte se s lékařem.",
    "Ochrana očí není nutná, je to naprosto neškodné.", "Moje fibromyalgie zmizela po třech týdnech.", "Zaručeně vám do 30 dnů dorostou vlasy a přestanou vypadávat.",
    "Rozlučte se s lékařem.", "Tento produkt netvrdí nic o růstu ani vypadávání vlasů.", "Zastaví bolest okamžitě.", "Stops pain instantly.",
    "Zrychluje hojení jizev.", "Speeds scar healing.", "Panel není schválen FDA a není zdravotnický prostředek.", "Schváleno ministerstvem zdravotnictví jako terapeutické zařízení.",
    # second round: cure verbs, medication idioms and comparisons, guarantees, protection against disease, clean look-alikes
    "Léčebné účinky červeného světla.", "Světlo, které léčí.", "Panel pomáhá tělu léčit se samo.", "Lepší než prášky.", "Je to přírodní alternativa k lékům.",
    "Nahrazuje fyzioterapii.", "Chraňte své zdraví před nemocemi.", "Redukuje stres a úzkost.", "Léčebný panel pro domácí použití.", "Redukuje otoky.",
    "Heals your body with light.", "Cures sore muscles overnight.", "Red light may heal sore muscles after training.", "Say goodbye to your painkillers.",
    "Better than medication.", "Natural alternative to painkillers.", "Protects your body against disease.", "Therapeutic device for home use.",
    "The healing power of red light.", "Trusted by doctors worldwide.", "Zaručeně zlepší váš spánek.", "Zázračné světlo pro celé tělo.",
    "Guaranteed results for everyone.", "Miracle light for your whole body.", "Zlepšuje krevní oběh.", "Pomáhá odstranit únavu.", "Zpomaluje stárnutí.",
    "Treat yourself to a red light session.", "Při používání chraňte oči ochrannými brýlemi.", "Protect your eyes from the light.", "30-day money-back guarantee.",
    "Garantujeme vrácení peněz do 30 dnů.", "This device does not cure anything.", "Panel nechrání před nemocemi.", "Ochrana před přehřátím.",
    "Light is not a substitute for medical advice.", "Light that heals. Light that may support muscle recovery.",
    # the approved category name "terapie červeným světlem" skips only the note about the word therapy
    "Terapie červeným světlem pro každý den.", "Terapie červeným a infračerveným světlem doma.", "Red light therapy for athletes.",
    "Terapie červeným světlem léčí bolest zad.", "Terapie červeným světlem na bolest zad.", "Světelná terapie pro vás.",
    "Terapie červeným světlem a také terapie.", "Zájem o terapii červeným světlem roste.", "Neslouží jako terapie nemocí.",
    # people with problems (the personas "everyday" and "seniors"): addressing a problem is a claim, even as a question
    "Máte problémy se spánkem? Světlo vám pomůže.", "Trpíte únavou? Zkuste světlo.", "Pomůže vám s problémy, které vás trápí.",
    "Světlo pro lepší pohyblivost kloubů.", "Panel na klouby.", "Máte potíže s pohybem? Světelný panel je řešení.", "Do you have problems with sleep? Try our panel.",
    "It helps you with everyday problems.", "Pomůže vám s výběrem panelu.", "Máte zájem o panel? Napište nám.", "Klidná večerní rutina se světlem.",
]


def main() -> None:
    vertical = load_vertical("pbm")
    profile = claims.load_profile("pbm")
    cases = []
    for text in CS + EN + MIXED:
        hits = profile.scan_text(text)
        cases.append({"text": text, "hits": [
            {"code": h.code, "topic": h.topic.id if h.topic else None, "start": h.start, "end": h.end} for h in sorted(hits, key=lambda h: (h.start, h.end, h.code))
        ]})
    out = ROOT / "web" / "tests" / "claims.golden.json"
    out.write_text(json.dumps({"rules": vertical.claim_rules(), "cases": cases}, ensure_ascii=False, indent=1) + "\n", "utf-8")
    n_hits = sum(len(c["hits"]) for c in cases)
    print(f"wrote {len(cases)} cases ({n_hits} hits) to {out}")


if __name__ == "__main__":
    main()
