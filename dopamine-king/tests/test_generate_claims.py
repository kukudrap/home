"""Claims profile (wellness): medical claims, hedging, status, safety, usage figures, negation, data hygiene."""
import json
import unittest
from pathlib import Path

from dopamine_king.generate import claims
from dopamine_king.generate.guard import TrustShield
from dopamine_king.generate.types import Brief, Draft

DATA = Path(__file__).resolve().parent.parent / "src" / "dopamine_king" / "data" / "verticals" / "pbm"
CS = Brief(brand="MITO LIGHT", topic="fotobiomodulace", audience="sportovci", lang="cs", vertical="pbm", claims_profile="wellness")
EN = Brief(brand="MITO LIGHT", topic="red light panels", audience="athletes", lang="en", vertical="pbm", claims_profile="wellness")
GENERAL = Brief(brand="Zorvia", topic="running shoes", audience="beginners")
SH = TrustShield()
IGNORED = {"AI_DISCLOSURE_REMINDER"}


def codes(text: str, brief: Brief = CS, **kw) -> set[str]:
    return {i.code for i in SH.check(text, brief, **kw) if i.code not in IGNORED}


class TermCompilerTests(unittest.TestCase):
    def test_terms_are_folded_and_wildcards_are_per_word(self):
        import re
        rx = re.compile(claims.terms_regex(["léč*", "zdravotnick* prostředek", "FDA approved"]))
        for hit in ("lecba", "lecit", "zdravotnicky prostredek", "zdravotnicke prostredek", "fda approved", "fda-approved"):
            self.assertTrue(rx.search(hit), hit)
        self.assertFalse(rx.search("velec"))                 # no match inside a word

    def test_empty_term_list_never_matches(self):
        import re
        self.assertFalse(re.search(claims.terms_regex([]), "anything at all"))

    def test_proximity_never_crosses_a_sentence_end(self):
        import re
        rx = re.compile(claims.proximity(r"\bleci\b", r"\bbolest\b"))
        self.assertTrue(rx.search("leci bolest"))
        self.assertTrue(rx.search("bolest se leci"))
        self.assertFalse(rx.search("leci. bolest"))
        self.assertFalse(rx.search("leci jedna dve tri ctyri pet sest sedm bolest"))


class MedicalClaimTests(unittest.TestCase):
    BAD_CS = [
        "Červené světlo léčí bolest kloubů.", "Panel zmírňuje zánět a bolest zad.", "Vyléčí depresi i úzkost.",
        "Podporuje růst vlasů.", "Červené světlo pomáhá při artritidě.", "Světlo na bolest zad.", "Panel proti migréně",
        "Zmírňuje depresi", "Urychluje hojení ran.", "Zlepšuje zrak u seniorů.", "Pomáhá při nespavosti.",
    ]
    BAD_EN = [
        "Red light cures joint pain.", "It relieves inflammation and back pain.", "Treats depression and anxiety.",
        "Red light for hair loss.", "Speeds up wound healing.", "Improves eyesight in older adults.", "Helps with insomnia.",
        "A panel for arthritis.", "Reduces swelling.",
    ]

    def test_czech_medical_claims_are_errors(self):
        for text in self.BAD_CS:
            found = {i.code: i.severity for i in SH.check(text, CS)}
            self.assertTrue({"CLAIM_MEDICAL", "DISEASE_MENTION"} & set(found), text)
            self.assertEqual(found.get("CLAIM_MEDICAL", found.get("DISEASE_MENTION")), "error", text)

    def test_english_medical_claims_are_errors(self):
        for text in self.BAD_EN:
            found = {i.code: i.severity for i in SH.check(text, EN)}
            self.assertTrue({"CLAIM_MEDICAL", "DISEASE_MENTION"} & set(found), text)

    def test_czech_without_diacritics_is_caught_too(self):
        self.assertIn("CLAIM_MEDICAL", codes("Cervene svetlo leci bolest kloubu."))
        self.assertIn("CLAIM_MEDICAL", codes("Pomaha pri artritide."))

    def test_message_names_the_topic_label_and_safer_wording(self):
        issue = next(i for i in SH.check("Červené světlo léčí bolest kloubů.", CS) if i.code == "CLAIM_MEDICAL")
        self.assertIn("Bolest", issue.message)
        self.assertIn("Síla důkazů", issue.message)
        self.assertIn("Bezpečněji", issue.message)
        issue = next(i for i in SH.check("Red light cures joint pain.", EN) if i.code == "CLAIM_MEDICAL")
        self.assertIn("Evidence label", issue.message)

    def test_unsafe_topics_are_blocked(self):
        for text in ("Zvyšuje testosteron a plodnost.", "Detoxikuje tělo a posiluje imunitu."):
            self.assertIn("CLAIM_AVOID", codes(text), text)
        self.assertIn("CLAIM_AVOID", codes("Boosts testosterone.", EN))

    def test_the_verdict_is_blocked(self):
        issues = SH.check("Červené světlo léčí bolest kloubů.", CS)
        self.assertEqual(SH.verdict(issues), "blocked")

    def test_a_medical_hit_is_not_reported_twice(self):
        issues = SH.check("Detoxikuje tělo.", CS)
        self.assertEqual([i.code for i in issues if i.code in ("CLAIM_AVOID", "HEALTH_CLAIM")], ["CLAIM_AVOID"])

    def test_general_profile_is_untouched(self):
        for text in ("Červené světlo léčí bolest kloubů.", "Red light cures joint pain."):
            self.assertFalse({"CLAIM_MEDICAL", "DISEASE_MENTION", "CLAIM_UNHEDGED"} & codes(text, GENERAL), text)
        self.assertIn("HEALTH_CLAIM", codes("This cures cancer.", GENERAL))


class HedgingTests(unittest.TestCase):
    def test_unhedged_benefit_is_a_warning(self):
        for text, brief in (("Zlepšuje spánek a regeneraci svalů.", CS), ("Supports muscle recovery and sleep quality.", EN),
                            ("Aktivuje mitochondrie a zvyšuje produkci ATP.", CS), ("Boosts mitochondria and ATP production.", EN),
                            ("Posiluje energii a pohodu.", CS)):
            found = {i.code: i.severity for i in SH.check(text, brief)}
            self.assertEqual(found.get("CLAIM_UNHEDGED"), "warn", text)

    def test_hedged_benefit_passes(self):
        for text, brief in (
            ("U zdravých lidí může červené světlo před cvičením podpořit sportovní výkon.", CS),
            ("Červené světlo může podpořit regeneraci po tréninku.", CS),
            ("Red light may support muscle recovery after exercise in healthy adults.", EN),
            ("In a small study, red light was associated with better sleep quality, and results vary between people.", EN),
        ):
            self.assertNotIn("CLAIM_UNHEDGED", codes(text, brief), text)

    def test_a_citation_next_to_the_claim_counts_as_a_source(self):
        brief = Brief(brand="B", topic="t", audience="a", lang="en", vertical="pbm", claims_profile="wellness",
                      sources=[{"id": "s1", "title": "A trial", "claim": "x"}])
        self.assertNotIn("CLAIM_UNHEDGED", codes("Red light supports muscle recovery [[cite:s1]].", brief))

    def test_a_brand_approved_statement_in_the_facts_passes(self):
        brief = Brief(brand="B", topic="t", audience="a", lang="cs", vertical="pbm", claims_profile="wellness",
                      facts=["Přístroj je určen jako pomůcka k podpoře regenerace zdravého organismu."])
        self.assertNotIn("CLAIM_UNHEDGED", codes("MITO LIGHT je pomůcka k podpoře regenerace zdravého organismu.", brief))
        self.assertIn("CLAIM_UNHEDGED", codes("MITO LIGHT je pomůcka k podpoře regenerace zdravého organismu.", CS))

    def test_a_question_is_not_a_claim(self):
        self.assertFalse({"CLAIM_UNHEDGED", "CLAIM_MEDICAL"} & codes("Může červené světlo podpořit regeneraci po tréninku?"))
        self.assertFalse({"CLAIM_UNHEDGED", "CLAIM_MEDICAL"} & codes("Léčí červené světlo bolest zad?"))


class NegationTests(unittest.TestCase):
    OK = [
        ("Přístroj neslouží k léčbě nemocí a nenahrazuje lékařskou péči.", CS),
        ("Přístroj není zdravotnický prostředek.", CS),
        ("Přístroj nelze použít jako léčbu bolesti.", CS),
        ("The device does not treat disease and does not replace medical care.", EN),
        ("This is not a medical device and it cannot cure pain.", EN),
        ("It is not FDA approved and makes no medical claims.", EN),
    ]

    def test_disclaimers_are_not_flagged(self):
        for text, brief in self.OK:
            self.assertFalse({"CLAIM_MEDICAL", "DISEASE_MENTION", "STATUS_CLAIM", "HEALTH_CLAIM"} & codes(text, brief), text)

    def test_negation_does_not_leak_into_the_next_sentence(self):
        self.assertIn("CLAIM_MEDICAL", codes("Nebojte se. Červené světlo léčí bolest kloubů."))
        self.assertIn("CLAIM_MEDICAL", codes("It is simple. Red light cures joint pain.", EN))


class StatusAndSafetyTests(unittest.TestCase):
    def test_status_claims_are_errors_unless_the_facts_say_so(self):
        for text, brief in (("Panel je zdravotnický prostředek schválený FDA.", CS), ("FDA approved medical device.", EN),
                            ("Lékařsky doporučeno a v nemocniční kvalitě.", CS), ("Doctor recommended, medical grade.", EN)):
            self.assertIn("STATUS_CLAIM", codes(text, brief), text)
        backed = Brief(brand="B", topic="t", audience="a", lang="en", vertical="pbm", claims_profile="wellness",
                       facts=["The panel is ETL certified for electrical safety."])
        self.assertNotIn("STATUS_CLAIM", codes("The panel is ETL certified for electrical safety.", backed))

    def test_absolute_safety_claims_are_errors(self):
        for text, brief in (("Bez vedlejších účinků, bezpečné pro každého.", CS), ("Naprosto bezpečné a bez rizika.", CS),
                            ("No side effects, safe for everyone.", EN), ("It is completely safe and risk-free.", EN)):
            found = {i.code: i.severity for i in SH.check(text, brief)}
            self.assertEqual(found.get("SAFETY_ABSOLUTE"), "error", text)

    def test_outcome_promises_are_flagged(self):
        for text, brief in (("Za 4 týdny uvidíte výrazně méně vrásek.", CS), ("Do dvou týdnů pocítíte rozdíl, výsledky za 14 dní.", CS),
                            ("You will see fewer wrinkles in 4 weeks.", EN), ("Results in 14 days.", EN)):
            self.assertIn("OUTCOME_PROMISE", codes(text, brief), text)

    def test_usage_figures_must_come_from_the_facts(self):
        self.assertIn("DOSE_NOT_FROM_MANUAL", codes("Sezení trvá 10 minut z 15 cm."))
        self.assertIn("DOSE_NOT_FROM_MANUAL", codes("Sessions last 10 minutes at 15 cm.", EN))
        backed = Brief(brand="B", topic="t", audience="a", lang="cs", vertical="pbm", claims_profile="wellness",
                       facts=["Výrobce doporučuje sezení 10 minut ze vzdálenosti 15 cm."])
        self.assertNotIn("DOSE_NOT_FROM_MANUAL", codes("Sezení trvá 10 minut z 15 cm.", backed))

    def test_numbers_that_are_not_usage_are_left_alone(self):
        self.assertNotIn("DOSE_NOT_FROM_MANUAL", codes("Jak vybrat panel za 5 minut"))
        self.assertNotIn("DOSE_NOT_FROM_MANUAL", codes("Read the guide in 5 minutes.", EN))

    def test_therapy_word_is_only_a_note(self):
        found = {i.code: i.severity for i in SH.check("Světelná terapie", CS)}
        self.assertEqual(found.get("THERAPY_WORD"), "info")
        self.assertEqual(SH.verdict(SH.check("Světelná terapie", CS)), "ok")

    def test_long_form_needs_a_safety_note(self):
        draft = Draft(format="seo_article", lang="cs", hook="Jak vybrat panel", body="Jak vybrat panel podle vlnových délek a plochy.")
        self.assertIn("SAFETY_NOTE_MISSING", {i.code for i in SH.check(draft, CS)})
        draft.body += " Nedívejte se dlouho přímo do světelného zdroje a řiďte se návodem výrobce."
        self.assertNotIn("SAFETY_NOTE_MISSING", {i.code for i in SH.check(draft, CS)})
        short = Draft(format="linkedin_post", lang="cs", hook="Panel", body="Jak vybrat panel podle vlnových délek.")
        self.assertNotIn("SAFETY_NOTE_MISSING", {i.code for i in SH.check(short, CS)})

    def test_approved_text_marked_exempt_is_not_judged(self):
        footer = "Přístroj slouží k podpoře regenerace zdravého organismu a nenahrazuje lékařskou péči."
        draft = Draft(format="newsletter", lang="cs", hook="x", body="Úvod.\n\n" + footer,
                      parts={"guard_exempt": [footer]})
        self.assertNotIn("CLAIM_UNHEDGED", {i.code for i in SH.check(draft, CS)})
        draft.parts = {}
        self.assertIn("CLAIM_UNHEDGED", {i.code for i in SH.check(draft, CS)})

    def test_placeholders_are_not_judged(self):
        draft = Draft(format="linkedin_post", lang="en", hook="x",
                      body="[[ADD: Explain how red light cures pain and improves sleep in 4 weeks]]")
        self.assertFalse({"CLAIM_MEDICAL", "CLAIM_UNHEDGED", "OUTCOME_PROMISE"} & {i.code for i in SH.check(draft, EN)})


class CompliantCopyTests(unittest.TestCase):
    GOOD_CS = [
        "Mnoho lidí zařazuje sezení pod červeným světlem do večerní rutiny.",
        "Podle návodu výrobce se panel používá z doporučené vzdálenosti.",
        "Fotobiomodulace je název pro působení červeného a blízkého infračerveného světla na buňky.",
        "Jak vybrat panel: vlnové délky, výkon a velikost plochy",
        "Panel má 408 LED diod a šest vlnových délek.",
        "Před prvním použitím si přečtěte návod a chraňte si oči.",
        "Kdo by měl před použitím světelného přístroje zajít za lékařem?",
    ]
    GOOD_EN = [
        "Many people add a red light session to an evening routine.",
        "How to choose a panel: wavelengths, power and size.",
        "Can red light support recovery after training?",
        "Read the manufacturer's instructions and protect your eyes.",
        "The panel has 408 LEDs and six wavelengths.",
    ]

    def test_compliant_copy_has_no_errors_or_warnings(self):
        for text in self.GOOD_CS:
            self.assertEqual(codes(text, CS) - {"THERAPY_WORD"}, set(), text)
        for text in self.GOOD_EN:
            self.assertEqual(codes(text, EN) - {"THERAPY_WORD"}, set(), text)


class IndependentExamplesTests(unittest.TestCase):
    """Wording written by the regulation research run, not by the rule author: a check on blind spots."""

    @classmethod
    def setUpClass(cls):
        cls.examples = json.loads((DATA / "examples.json").read_text("utf-8"))

    def brief(self, lang):
        return Brief(brand="MITO LIGHT", topic="red light panels", audience="x", lang=lang, vertical="pbm", claims_profile="wellness",
                     facts=[self.examples["brand_purpose_fact"][lang]])

    def test_unsafe_wording_is_blocked(self):
        for lang in ("en", "cs"):
            for text in self.examples["unsafe"][lang]:
                errors = [i.code for i in SH.check(text, self.brief(lang)) if i.severity == "error"]
                self.assertTrue(errors, text)

    def test_safe_wording_passes_cleanly(self):
        for lang in ("en", "cs"):
            for text in self.examples["safe"][lang]:
                found = [(i.code, i.severity) for i in SH.check(text, self.brief(lang)) if i.severity != "info"]
                self.assertEqual(found, [], text)

    def test_medication_advice_and_testimonials_are_caught(self):
        for text in ("Replace your painkillers with red light.", "Nahraďte léky světlem a přestaňte užívat léky.",
                     "Say goodbye to your doctor.", "Moje fibromyalgie zmizela po třech týdnech.", "My arthritis vanished in a month."):
            self.assertTrue(codes(text, EN if text.isascii() else CS) & {"MEDICATION_ADVICE", "CLAIM_MEDICAL", "DISEASE_MENTION"}, text)

    def test_ads_that_address_people_with_a_condition_are_caught_even_as_questions(self):
        for text in ("Trpíte artritidou? Vyzkoušejte panel.", "Do you suffer from migraines? Try our panel.", "Pro lidi s cukrovkou: nový panel."):
            self.assertIn("DISEASE_MENTION", codes(text, EN if text.isascii() else CS), text)

    def test_standard_disclaimers_and_commerce_phrases_are_not_flagged(self):
        for text in ("This device is not intended to diagnose, treat, cure, or prevent any disease.", "Risk-free trial for 60 days.",
                     "People with epilepsy should ask a doctor first.", "Přístroj neslouží k diagnostice, léčbě ani prevenci nemocí.",
                     "Vyzkoušejte bez rizika, bezpečná platba.", "Jste-li těhotná, poraďte se s lékařem."):
            found = codes(text, EN if text.isascii() else CS)
            self.assertEqual(found & {"CLAIM_MEDICAL", "DISEASE_MENTION", "SAFETY_ABSOLUTE", "STATUS_CLAIM", "MEDICATION_ADVICE"}, set(), text)

    def test_a_new_clause_ends_the_negation(self):
        self.assertIn("SAFETY_ABSOLUTE", codes("Ochrana očí není nutná, je to naprosto neškodné."))
        self.assertIn("SAFETY_ABSOLUTE", codes("You do not need eye protection, it is completely harmless.", EN))


class CureVerbAndPromiseTests(unittest.TestCase):
    """Second round: a fresh batch of sentences probed after the first rules were written (cure verbs, medication idioms, guarantees)."""

    BLOCKED_CS = [
        "Léčebné účinky červeného světla.", "Světlo, které léčí.", "Panel pomáhá tělu léčit se samo.", "Lepší než prášky.",
        "Je to přírodní alternativa k lékům.", "Nahrazuje fyzioterapii.", "Chraňte své zdraví před nemocemi.",
        "Redukuje stres a úzkost.", "Léčebný panel pro domácí použití.", "Rozlučte se s prášky na bolest.", "Redukuje otoky.",
    ]
    BLOCKED_EN = [
        "Heals your body with light.", "Cures sore muscles overnight.", "Say goodbye to your painkillers.", "Better than medication.",
        "Natural alternative to painkillers.", "Protects your body against disease.", "Therapeutic device for home use.",
        "The healing power of red light.", "Trusted by doctors worldwide.",
    ]
    CLEAN = [
        ("Treat yourself to a red light session.", EN), ("Při používání chraňte oči ochrannými brýlemi.", CS),
        ("Protect your eyes from the light.", EN), ("30-day money-back guarantee.", EN), ("Garantujeme vrácení peněz do 30 dnů.", CS),
        ("This device does not cure anything.", EN), ("Panel nechrání před nemocemi.", CS), ("Ochrana před přehřátím.", CS),
        ("Light is not a substitute for medical advice.", EN), ("Pro lepší pohodu večer: krátké světelné sezení.", CS),
    ]

    def errors(self, text, brief):
        return {i.code for i in SH.check(text, brief) if i.severity == "error"}

    def test_cure_verbs_and_medication_idioms_are_errors(self):
        for text in self.BLOCKED_CS:
            self.assertTrue(self.errors(text, CS), text)
        for text in self.BLOCKED_EN:
            self.assertTrue(self.errors(text, EN), text)

    def test_a_cure_verb_lifts_a_wellness_topic_to_a_medical_claim_even_when_hedged(self):
        self.assertIn("CLAIM_MEDICAL", codes("Cures sore muscles overnight.", EN))
        self.assertIn("CLAIM_MEDICAL", codes("Red light may heal sore muscles after training.", EN))
        self.assertNotIn("CLAIM_MEDICAL", codes("Red light may support muscle recovery after training.", EN))

    def test_a_cure_verb_alone_is_a_claim_with_a_generic_topic(self):
        hits = claims.load_profile("pbm").scan_text("Light that heals.")
        self.assertEqual([(h.code, h.topic.id) for h in hits], [("CLAIM_MEDICAL", "generic-cure")])

    def test_guarantees_and_miracles_are_promises(self):
        for text, brief in (("Zaručeně zlepší váš spánek.", CS), ("Guaranteed results for everyone.", EN), ("Zázračné světlo pro celé tělo.", CS),
                            ("Miracle light for your whole body.", EN)):
            self.assertIn("OUTCOME_PROMISE", codes(text, brief), text)

    def test_ordinary_wording_is_not_blocked(self):
        for text, brief in self.CLEAN:
            self.assertEqual(self.errors(text, brief), set(), text)
        for text in ("30-day money-back guarantee.", "Garantujeme vrácení peněz do 30 dnů."):
            self.assertNotIn("OUTCOME_PROMISE", codes(text, EN if text.isascii() else CS), text)

    def test_the_generic_topic_comes_from_the_data(self):
        profile = claims.load_profile("pbm")
        ids = [t.id for t in profile.topics]
        self.assertIn("generic-cure", ids)
        self.assertEqual(ids.count("generic-cure"), 1)
        generic = next(t for t in profile.topics if t.id == "generic-cure")
        self.assertEqual(generic.klass, "medical")
        self.assertTrue(generic.safe("cs") and generic.safe("en"))


class ApprovedCategoryNameTests(unittest.TestCase):
    """The brand's own category name ("terapie červeným světlem") is approved: only the note about the word therapy skips it."""

    def test_the_approved_name_is_not_noted_in_any_case_or_language(self):
        for text, brief in (("Terapie červeným světlem pro každý den.", CS), ("Terapie červeným a infračerveným světlem doma.", CS),
                            ("Zájem o terapii červeným světlem roste.", CS), ("Red light therapy for athletes.", EN),
                            ("Near-infrared light therapy at home.", EN)):
            self.assertNotIn("THERAPY_WORD", codes(text, brief), text)

    def test_other_uses_of_the_word_are_still_noted(self):
        for text, brief in (("Světelná terapie pro vás.", CS), ("Naše terapie pomáhá.", CS), ("Our therapy helps.", EN)):
            self.assertIn("THERAPY_WORD", codes(text, brief), text)
        self.assertIn("THERAPY_WORD", codes("Terapie červeným světlem a také terapie.", CS))           # the second use is not the name

    def test_the_approved_name_never_hides_a_medical_claim(self):
        for text, brief in (("Terapie červeným světlem léčí bolest zad.", CS), ("Terapie červeným světlem na bolest zad.", CS),
                            ("Red light therapy cures joint pain.", EN)):
            self.assertIn("CLAIM_MEDICAL", codes(text, brief), text)

    def test_a_negated_use_is_not_noted(self):
        self.assertNotIn("THERAPY_WORD", codes("Neslouží jako terapie nemocí.", CS))


class DataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.claims = json.loads((DATA / "claims.json").read_text("utf-8"))
        cls.guard = json.loads((DATA / "guard.json").read_text("utf-8"))

    def test_no_long_dashes(self):
        for name in ("claims.json", "guard.json"):
            text = (DATA / name).read_text("utf-8")
            self.assertNotIn(chr(0x2014), text, name)
            self.assertNotIn(chr(0x2013), text, name)

    def test_topics_are_well_formed(self):
        ids = [t["id"] for t in self.claims["topics"]]
        self.assertEqual(len(ids), len(set(ids)))
        for t in self.claims["topics"]:
            self.assertIn(t["class"], claims.CLASS_RANK, t["id"])
            self.assertIn(t["label_cap"], ("strong", "moderate", "limited", "contested", "none"), t["id"])
            self.assertTrue(t["name_en"] and t["name_cs"] and t["claim_en"] and t["claim_cs"], t["id"])
            self.assertTrue(t["safe_en"] and t["safe_cs"], t["id"])
            if t["class"] in ("wellness", "cosmetic", "medical", "avoid"):
                self.assertTrue(t["nouns_en"] and t["nouns_cs"], t["id"])

    def test_every_blocked_class_topic_is_caught_by_its_own_words(self):
        profile = claims.load_profile("pbm")
        for t in profile.topics:
            if t.klass not in ("medical", "avoid") or not t.nouns:        # the generic cure topic has words of its own, no nouns
                continue
            noun_en = next(n for n in t.nouns if n.replace("*", "").isascii() and len(n) > 4 and "*" not in n and " " not in n)
            found = codes(f"Red light cures {noun_en}.", EN)
            self.assertTrue({"CLAIM_MEDICAL", "CLAIM_AVOID", "DISEASE_MENTION"} & found, (t.id, noun_en, found))

    def test_guard_lists_are_complete_in_both_languages(self):
        for key in ("treatment_verbs", "benefit_verbs", "disease_terms", "device_words", "regulated_status", "safety_absolute",
                    "hedge_words", "safety_terms", "negation_words", "therapy_words"):
            minimum = 2 if key == "therapy_words" else 3
            self.assertGreaterEqual(len(self.guard[key]["en"]), minimum, key)
            self.assertGreaterEqual(len(self.guard[key]["cs"]), minimum, key)
        for lang in ("cs", "en"):
            self.assertTrue(self.guard["safety_footer"][lang].strip())
            self.assertTrue(self.guard["writer_rules"][lang])

    def test_the_safety_footer_itself_passes_the_shield(self):
        for lang, brief in (("cs", CS), ("en", EN)):
            footer = self.guard["safety_footer"][lang]
            draft = Draft(format="newsletter", lang=lang, hook="x", body=footer, parts={"guard_exempt": [footer]})
            bad = {i.code for i in SH.check(draft, brief) if i.severity != "info"}
            self.assertEqual(bad, set(), (lang, bad))

    def test_profile_for_picks_the_profile_from_the_brief(self):
        self.assertIsNone(claims.profile_for(GENERAL))
        self.assertIsNotNone(claims.profile_for(CS))
        self.assertIs(claims.profile_for(CS), claims.profile_for(EN))      # cached per vertical


if __name__ == "__main__":
    unittest.main()
