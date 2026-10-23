"""The emotional claim bank: every sentence passes the Trust Shield, rests on the brand file and never states an effect on the body."""
import json
import unittest
from pathlib import Path

from dopamine_king.generate.guard import TrustShield
from dopamine_king.radar import emotion as E
from dopamine_king.verticals import load_vertical

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "radar" / "claims_emotional.json"
DATA = E.load(PATH)
V = load_vertical("pbm")
LEDGER = V.ledger()
RESULTS = E.check_claims(DATA, V, LEDGER)
CLAIMS = {c["id"]: c for c in DATA["claims"]}
PERSONAS = {p["id"] for p in V.personas()}
BODY_WORDS = ("dopamin", "serotonin", "endorfin", "oxytocin", "hormon", "kortizol", "nálad", "spán", "energi", "stres", "úzkost", "únav", "bolest", "léč",
              "zdrav", "relax", "uklid", "zklid", "pohod", "regener", "detox", "imunit", "vrás", "kůž", "pleť", "sval")


class StructureTests(unittest.TestCase):
    def test_the_file_is_plain_data_with_no_long_dash(self):
        text = PATH.read_text("utf-8")
        self.assertNotIn(chr(0x2014), text)
        self.assertNotIn(chr(0x2013), text)
        self.assertEqual(json.loads(text), DATA)

    def test_ids_and_texts_are_unique(self):
        self.assertEqual(len(CLAIMS), len(DATA["claims"]))
        texts = [c["text"] for c in DATA["claims"]]
        self.assertEqual(len(set(texts)), len(texts))

    def test_every_claim_has_a_known_lever_use_and_persona(self):
        levers = {lv["id"] for lv in DATA["levers"]}
        for c in DATA["claims"]:
            self.assertIn(c["lever"], levers, c["id"])
            self.assertIn(c["use"], E.USES, c["id"])
            self.assertIn(c["use"], DATA["uses"], c["id"])
            self.assertTrue(set(c.get("personas", [])) <= PERSONAS, c["id"])
            self.assertTrue(set(c.get("support", [])) <= set(DATA["facts"]), c["id"])

    def test_every_persona_has_claims_and_the_other_lists_are_not_empty(self):
        for pid in PERSONAS:
            self.assertGreaterEqual(len([c for c in DATA["claims"] if pid in c.get("personas", [])]), 3, pid)
        self.assertGreaterEqual(len([c for c in DATA["claims"] if c["use"] == "tagline"]), 5)
        self.assertGreaterEqual(len([c for c in DATA["claims"] if c["use"] == "microcopy"]), 8)
        self.assertGreaterEqual(len(DATA["story"]), 3)

    def test_the_levers_stand_on_tactics_of_the_ledger(self):
        for lv in DATA["levers"]:
            self.assertTrue(lv["tactics"], lv["id"])
            for tid in lv["tactics"]:
                self.assertIn(tid, LEDGER.tactics, (lv["id"], tid))
            self.assertTrue(lv["what_cs"] and lv["watch_cs"], lv["id"])

    def test_picks_say_why_and_a_concept_says_what_to_decide(self):
        picks = [c for c in DATA["claims"] if c.get("pick")]
        self.assertTrue(8 <= len(picks) <= 12, len(picks))
        for c in picks:
            self.assertTrue(c.get("why_cs"), c["id"])
        for c in DATA["claims"]:
            if c.get("concept"):
                self.assertTrue(c.get("needs"), c["id"])
            if c.get("where_cs"):
                self.assertEqual(c["use"], "microcopy", c["id"])

    def test_ab_tests_compare_two_different_existing_claims(self):
        for t in DATA["tests"]:
            self.assertIn(t["a"], CLAIMS)
            self.assertIn(t["b"], CLAIMS)
            self.assertNotEqual(t["a"], t["b"])
            self.assertTrue(t["hypothesis_cs"])

    def test_guardrails_name_tactics_that_exist(self):
        for g in DATA["guardrails"]:
            if g.get("tactic"):
                self.assertIn(g["tactic"], LEDGER.tactics, g["title_cs"])


class FactTests(unittest.TestCase):
    def test_every_fact_a_claim_rests_on_is_in_the_brand_file(self):
        self.assertEqual(E.facts_problems(DATA, V), [])

    def test_a_number_needs_a_fact_or_is_a_concept(self):
        for c in DATA["claims"]:
            if E.has_number(c["text"]):
                self.assertTrue(c.get("support") or c.get("concept"), c["id"])

    def test_has_number(self):
        self.assertTrue(E.has_number("Sedm večerů, sedm malých vítězství."))
        self.assertTrue(E.has_number("Šest vlnových délek."))
        self.assertTrue(E.has_number("Panel 5.0 má čtyři režimy."))
        self.assertFalse(E.has_number("Ještě poslední e-mail. Pak je řada na vás."))
        self.assertFalse(E.has_number("Za týden se ozveme."))

    def test_the_brief_of_a_claim_carries_the_facts_it_rests_on_and_the_base_is_untouched(self):
        base = V.briefs(LEDGER)["mito-light-cs"]
        item = CLAIMS["pribeh-01"]
        brief = E.brief_for(base, DATA, item)
        self.assertEqual(len(brief.facts), len(base.facts) + len(item["support"]))
        self.assertIn(DATA["facts"]["pocatek-posilovna"]["text"], brief.facts)
        self.assertEqual(E.brief_for(base, DATA, CLAIMS["tesit-01"]).facts, base.facts)


class ShieldTests(unittest.TestCase):
    def test_every_claim_passes_the_trust_shield_with_no_error_and_no_warning(self):
        for cid, verdict in RESULTS.items():
            self.assertEqual(verdict, {"errors": [], "warnings": []}, (cid, CLAIMS[cid]["text"]))
        self.assertEqual(len(RESULTS), len(DATA["claims"]))

    def test_the_story_and_the_naming_pass_too(self):
        base = V.briefs(LEDGER)["mito-light-cs"]
        shield = TrustShield(LEDGER)
        for item in DATA["story"]:
            self.assertEqual(E.judge(shield, item["text"], E.brief_for(base, DATA, item)), {"errors": [], "warnings": []}, item["id"])

    def test_no_claim_or_story_names_the_body_a_mood_a_hormone_or_a_superlative(self):
        texts = [c["text"] for c in DATA["claims"]] + [s["text"] for s in DATA["story"]]
        for text in texts:
            low = text.lower()
            for word in BODY_WORDS + E.SUPERLATIVES:
                self.assertNotIn(word, low, text)

    def test_the_judge_catches_what_the_bank_must_never_say(self):
        base = V.briefs(LEDGER)["mito-light-cs"]
        shield = TrustShield(LEDGER)
        self.assertIn("CLAIM_MEDICAL", E.judge(shield, "Zvyšuje dopamin a zlepšuje náladu.", base)["errors"])
        self.assertIn("OUTCOME_PROMISE", E.judge(shield, "Za 14 dní nový člověk.", base)["warnings"])
        self.assertEqual(E.judge(shield, "Těšte se na konec dne.", base), {"errors": [], "warnings": []})

    def test_every_forbidden_wording_is_caught_and_its_replacement_is_clean(self):
        rows = E.check_forbidden(DATA, V, LEDGER)
        self.assertEqual(len(rows), len(DATA["forbidden"]))
        self.assertGreaterEqual(len(rows), 8)
        for row in rows:
            self.assertTrue(set(row["expect"]) <= set(row["found"]), (row["text"], row["found"]))
            self.assertEqual(row["swap_verdict"], {"errors": [], "warnings": []}, (row["text"], row["swap"]))


class SectionTests(unittest.TestCase):
    SECTION = E.section_data(DATA, V, LEDGER, V.personas())

    def test_every_claim_is_listed_exactly_once_besides_the_picks(self):
        s = self.SECTION
        listed = [c["id"] for lv in s["levers"] for c in lv["claims"]] + [c["id"] for p in s["personas"] for c in p["claims"]] \
            + [c["id"] for c in s["taglines"]] + [c["id"] for c in s["microcopy"]]
        self.assertEqual(sorted(listed), sorted(CLAIMS))
        self.assertEqual(s["totals"], {"claims": len(CLAIMS), "picks": len(s["picks"]), "concepts": sum(bool(c.get("concept")) for c in DATA["claims"]),
                                       "errors": 0, "warnings": 0})

    def test_a_lever_is_as_strong_as_its_weakest_tactic_and_counts_only_verified_studies(self):
        for lv in self.SECTION["levers"]:
            labels = [e["label"] for e in lv["evidence"]]
            self.assertEqual(E.LABEL_RANK[lv["label"]], min(E.LABEL_RANK[x] for x in labels), lv["id"])
            for e in lv["evidence"]:
                self.assertEqual(e["n_verified"], len(e["studies"]), e["id"])
                for study in e["studies"]:
                    self.assertTrue(study["url"], study["title"])
        weak = E.lever_summary([{"label": "strong", "studies": [{"url": "u1", "title": "a"}]}, {"label": "limited", "studies": [{"url": "u1", "title": "a"}, {"url": "u2", "title": "b"}]}])
        self.assertEqual(weak, {"label": "limited", "n_verified": 2})
        self.assertEqual(E.lever_summary([]), {"label": "none", "n_verified": 0})

    def test_the_dopamine_block_explains_why_the_word_is_not_used(self):
        d = self.SECTION["dopamine"]
        self.assertIn("není jednoduchá chemická látka", d["summary"])
        self.assertGreaterEqual(d["n_verified"], 3)
        self.assertEqual(d["n_verified"], len(d["studies"]))
        years = {s["year"] for s in d["studies"]}
        self.assertTrue({1998, 2011, 2014} <= years)

    def test_each_request_to_the_brand_is_listed_once_with_the_texts_it_concerns(self):
        needs = self.SECTION["needs"]
        self.assertEqual(len({n["need"] for n in needs}), len(needs))
        asked = {c["id"] for c in DATA["claims"] if c.get("needs")}
        self.assertTrue(asked)
        texts = {t for n in needs for t in n["texts"]}
        for cid in asked:
            self.assertIn(CLAIMS[cid]["text"], texts, cid)
        self.assertTrue(any("Červená hodina" in n["need"] for n in needs))
        merged = E.needs_list([{"text": "a", "needs": "x"}, {"text": "b", "needs": "x"}, {"text": "c"}], [{"name": "N", "needs": "x"}])
        self.assertEqual(merged, [{"need": "x", "texts": ["a", "b", "Název N"]}])


if __name__ == "__main__":
    unittest.main()
