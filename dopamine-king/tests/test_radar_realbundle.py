"""The real edition of the game: every duel, boss and card must trace back to a stored search, the ledger or the brand file."""
import json
import unittest
from collections import Counter
from pathlib import Path

from dopamine_king.generate.claims import load_profile
from dopamine_king.generate.guard import severity_of
from dopamine_king.radar import analyze as A
from dopamine_king.radar import realbundle as RB
from dopamine_king.radar.collect import load_plan, load_records
from dopamine_king.scoring import load_spec, score_hook
from dopamine_king.verticals import load_vertical

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "radar" / "snapshots" / "2026-10-23"
DRAFTS = ROOT / "radar" / "drafts" / "2026-10-23"
PLAN = ROOT / "radar" / "plan.json"
EM, EN = chr(0x2014), chr(0x2013)

VERT = load_vertical("pbm")
RECORDS = load_records(SNAPSHOT, load_plan(PLAN))
BY_ID = {r["id"]: r for r in RECORDS}
BUNDLE = RB.build_real_bundle(SNAPSHOT, DRAFTS, PLAN)
ARENA = BUNDLE["arena"]
PROFILE = load_profile("pbm", "wellness")
SPEC = load_spec()


def link_at(record: str, rank: int) -> dict:
    return next(l for l in BY_ID[record]["links"] if l["rank"] == rank)


def of_kind(kind: str) -> list[dict]:
    return [d for d in ARENA if d["kind"] == kind]


class TitleFilterTests(unittest.TestCase):
    def test_a_title_made_of_the_words_of_the_address_is_not_a_hook(self):
        self.assertTrue(RB.derived_from_address("cesi objevuji terapii cervenym svetlem roste", "https://forbes.cz/cesi-objevuji-terapii-cervenym-svetlem-roste/"))
        self.assertTrue(RB.derived_from_address("2385920 terapie cervenym svetlem 1 3 nebo 5 navstev", "https://www.slevomat.cz/akce/2385920-terapie-cervenym-svetlem-1-3-nebo-5-navstev"))
        self.assertFalse(RB.derived_from_address("Red Light Therapy for Better, Healthier Aging", "https://joovv.com/blogs/news/aging"))

    def test_identifiers_and_file_names_are_not_titles(self):
        self.assertTrue(RB.looks_like_code("ff36fa9f 079b 4a29 919e ab3e2c98a065"))
        self.assertTrue(RB.looks_like_code("16528 manual 2024 1 3"))
        self.assertFalse(RB.looks_like_code("Red Light Therapy 2025 Review: What Worked, What Failed"))

    def test_bands_targets_and_scores(self):
        self.assertEqual([RB.band(g, RB.GAP_BANDS) for g in (2, 3, 4, 5, 9)], ["hard", "medium", "medium", "easy", "easy"])
        self.assertEqual([RB.band(g, RB.REACH_BANDS) for g in (2, 4, 7, 8, 20)], ["hard", "medium", "medium", "easy", "easy"])
        self.assertEqual([RB.boss_target(p) for p in (0, 12, 54.9, 61, 77.1, 99)], [55, 55, 55, 65, 80, 90])
        self.assertEqual([RB.tier_of(p) for p in (55, 60, 65, 75, 80, 90)], [1, 1, 2, 2, 3, 3])
        self.assertEqual((RB.position_score(1, 10), RB.position_score(10, 10), RB.position_score(1, 1)), (100.0, 10.0, 100.0))
        self.assertEqual(RB.slug("Mito Red Light (USA)"), "mito-red-light-usa")


class BundleTests(unittest.TestCase):
    def test_it_carries_every_key_the_game_reads_and_the_new_ones(self):
        for key in ("meta", "spec", "calibration", "vertical", "claims", "claim_rules", "cohort_labels", "benchmarks", "arena", "bosses", "myths", "lab", "vault", "loot",
                    "forge_samples", "guru_sample", "guru_samples", "tasks", "market", "claimbank", "patterns"):
            self.assertIn(key, BUNDLE)

    def test_nothing_in_it_is_simulated(self):
        meta = BUNDLE["meta"]
        self.assertIs(meta["synthetic"], False)
        self.assertEqual(meta["edition"], "real")
        self.assertEqual(BUNDLE["patterns"], [])
        self.assertEqual(BUNDLE["lab"]["scenarios"], [])
        self.assertTrue(all(c["demo"] is False for c in BUNDLE["loot"]["cards"]))
        self.assertFalse(BUNDLE["calibration"]["fitted"])

    def test_the_counts_are_those_of_the_stored_snapshot(self):
        real = BUNDLE["meta"]["real"]
        manifest = json.loads((SNAPSHOT / "snapshot.json").read_text("utf-8"))
        self.assertEqual(real["searches"], len(RECORDS))
        self.assertEqual(real["links"], sum(len(r["links"]) for r in RECORDS))
        self.assertEqual(real["sites"], len({A.host_of(l["url"]) for r in RECORDS for l in r["links"]}))
        self.assertEqual(real["market_searches"], sum(1 for r in RECORDS if r["group"] in RB.MARKET_GROUPS))
        self.assertEqual((real["first"], real["last"], real["snapshot"]), (manifest["first_retrieved_at"], manifest["last_retrieved_at"], manifest["last_retrieved_at"][:10]))
        self.assertEqual(real["duels"], dict(Counter(d["kind"] for d in ARENA)))

    def test_it_is_deterministic(self):
        again = RB.build_real_bundle(SNAPSHOT, DRAFTS, PLAN)
        for b in (BUNDLE, again):
            b["meta"] = {k: v for k, v in b["meta"].items() if k != "generated"}
        self.assertEqual(json.dumps(BUNDLE, sort_keys=True), json.dumps(again, sort_keys=True))

    def test_no_long_dash_anywhere(self):
        text = json.dumps(BUNDLE, ensure_ascii=False)
        self.assertNotIn(EM, text)
        self.assertNotIn(EN, text)


class DuelTests(unittest.TestCase):
    def test_ids_are_unique_and_named_after_the_kind(self):
        ids = [d["id"] for d in ARENA]
        self.assertEqual(len(ids), len(set(ids)))
        for d in ARENA:
            self.assertTrue(d["id"].startswith(d["kind"] + "-"), d["id"])
            self.assertIn(d["difficulty"], ("easy", "medium", "hard"))
            self.assertIn(d["winner"], ("a", "b"))
            self.assertIn(d["lang"], ("cs", "en"))
            self.assertIs(type(d["upset"]), bool)
        self.assertEqual({d["kind"] for d in ARENA}, {"rank", "reach", "claim"})
        for kind in ("rank", "reach", "claim"):
            self.assertGreaterEqual(len(of_kind(kind)), 30, kind)

    def test_every_side_with_a_record_is_a_result_that_was_stored(self):
        for d in ARENA:
            for side in ("a", "b"):
                s = d[side]
                if "record" not in s:
                    continue
                link = link_at(s["record"], s["rank"])
                self.assertEqual(s["url"], link["url"], d["id"])
                self.assertEqual(s["text"], link["title"].strip(), d["id"])
                self.assertEqual(s["host"], A.host_of(link["url"]), d["id"])
                self.assertEqual(s["of"], len(BY_ID[s["record"]]["links"]), d["id"])

    def test_rank_duels_are_won_by_the_better_placed_result_of_the_same_search(self):
        for d in of_kind("rank"):
            a, b = d["a"], d["b"]
            self.assertEqual(a["record"], b["record"], d["id"])
            self.assertNotEqual(a["host"], b["host"], d["id"])
            self.assertEqual(d["query"], BY_ID[a["record"]]["query"])
            self.assertGreaterEqual(abs(a["rank"] - b["rank"]), RB.GAP_BANDS[-1][1], d["id"])
            self.assertEqual(d["winner"], "a" if a["rank"] < b["rank"] else "b", d["id"])
            self.assertEqual(d["winner"], "a" if a["success"] > b["success"] else "b", d["id"])
            self.assertEqual(d["difficulty"], RB.band(abs(a["rank"] - b["rank"]), RB.GAP_BANDS), d["id"])
            self.assertEqual(a["success"], RB.position_score(a["rank"], a["of"]))
            self.assertIn(BY_ID[a["record"]]["group"], RB.MARKET_GROUPS)

    def test_the_scores_in_a_duel_are_what_the_scorer_gives(self):
        for d in of_kind("rank") + of_kind("claim"):
            for side in ("a", "b"):
                s = d[side]
                self.assertEqual(s["score"], round(score_hook(s["text"], lang=s["lang"], spec=SPEC).total, 1), (d["id"], side))

    def test_an_upset_is_a_confident_model_that_was_wrong(self):
        for d in of_kind("rank"):
            gap = d["a"]["score"] - d["b"]["score"]
            model_pick = "a" if gap > 0 else "b"
            confident = abs(d["a"]["score"] - d["b"]["score"]) >= RB.UPSET_MIN_GAP - 0.11     # scores are rounded to one decimal
            if d["upset"]:
                self.assertTrue(confident and model_pick != d["winner"], d["id"])
            elif confident:
                self.assertEqual(model_pick, d["winner"], d["id"])
        self.assertTrue(any(d["upset"] for d in of_kind("rank")))

    def test_reach_duels_count_the_market_searches_a_site_appeared_in(self):
        market = {r["id"] for r in RECORDS if r["group"] in RB.MARKET_GROUPS}
        for d in of_kind("reach"):
            for side in ("a", "b"):
                s = d[side]
                seen = {r["id"] for r in RECORDS if r["id"] in market and any(A.host_of(l["url"]) == s["host"] for l in r["links"])}
                self.assertEqual(set(s["searches"]), seen, (d["id"], s["host"]))
                self.assertEqual(s["count"], len(seen))
                self.assertEqual(s["of"], len(market))
            a, b = d["a"], d["b"]
            self.assertGreaterEqual(abs(a["count"] - b["count"]), RB.REACH_BANDS[-1][1])
            self.assertEqual(d["winner"], "a" if a["count"] > b["count"] else "b", d["id"])
            self.assertEqual(d["difficulty"], RB.band(abs(a["count"] - b["count"]), RB.REACH_BANDS))

    def test_claim_duels_pit_a_blocked_title_against_a_clean_one(self):
        for d in of_kind("claim"):
            flags = {s: d[s]["flagged"] for s in ("a", "b")}
            self.assertEqual(sorted(flags.values()), [False, True], d["id"])
            self.assertEqual(d["winner"], "a" if flags["a"] else "b", d["id"])
            for s in ("a", "b"):
                side = d[s]
                again = [(h.code, severity_of(h.code)) for h in PROFILE.scan_text(side["text"])]
                self.assertEqual([(f["code"], f["severity"]) for f in side["findings"]], again, (d["id"], s))
                if side["flagged"]:
                    self.assertTrue(any(f["severity"] == "error" for f in side["findings"]))
                    self.assertTrue(all(f["phrase"] in side["text"] for f in side["findings"]))
                else:
                    self.assertEqual(side["findings"], [])
                self.assertFalse(A.title_is_junk(side["text"], side["url"]))
                self.assertFalse(RB.derived_from_address(side["text"], side["url"]), side["text"])
            self.assertEqual(d["a"]["lang"], d["b"]["lang"])

    def test_the_model_accuracy_is_counted_over_all_pairs_and_reported_as_it_is(self):
        m = BUNDLE["meta"]["real"]["model"]
        self.assertGreater(m["pairs"], len(of_kind("rank")))
        self.assertLessEqual(m["decided"], m["pairs"])
        self.assertEqual(m["pct"], round(100.0 * m["right"] / m["decided"], 1))
        self.assertTrue(0 <= m["pct"] <= 100)


class BossTests(unittest.TestCase):
    def test_every_rival_is_a_stored_title(self):
        bosses = BUNDLE["bosses"]
        self.assertGreaterEqual(len(bosses), 15)
        self.assertEqual(len({b["id"] for b in bosses}), len(bosses))
        self.assertEqual(len({b["rival"]["text"] for b in bosses}), len(bosses))
        for b in bosses:
            r = b["rival"]
            link = link_at(r["record"], r["rank"])
            self.assertEqual((r["url"], r["text"]), (link["url"], link["title"].strip()), b["id"])
            self.assertTrue(55 <= b["percentile"] <= 90, b["id"])
            self.assertEqual(b["tier"], RB.tier_of(b["percentile"]))
            self.assertEqual(b["xp"], {1: 60, 2: 100, 3: 180}[b["tier"]])
            self.assertIn(b["cohort"], BUNDLE["benchmarks"])
            self.assertEqual(b["taunt_cs"], r["text"])
            self.assertEqual(r["score"], round(score_hook(r["text"], lang=r["lang"], spec=SPEC).total, 1))

    def test_a_brand_boss_is_a_page_of_that_brands_own_site(self):
        for b in BUNDLE["bosses"]:
            if not b["id"].startswith("boss-b-"):
                continue
            rec = BY_ID[b["rival"]["record"]]
            self.assertEqual(rec["group"], RB.SITE_GROUP)
            self.assertTrue(A.host_matches(b["rival"]["host"], rec["allowed_domains"]), b["id"])
            self.assertEqual(b["cohort"], "real-brands")

    def test_a_persona_boss_comes_from_a_search_of_that_persona(self):
        personas = {p["id"] for p in VERT.personas()}
        found = set()
        for b in BUNDLE["bosses"]:
            if b["id"].startswith("boss-p-"):
                rec = BY_ID[b["rival"]["record"]]
                self.assertIn(rec["persona"], personas)
                self.assertTrue(b["id"].startswith(f"boss-p-{rec['persona']}-"), b["id"])
                found.add(rec["persona"])
        self.assertGreaterEqual(len(found), 4)


class BenchmarkTests(unittest.TestCase):
    def test_the_benchmarks_are_the_scores_of_real_titles(self):
        for name, b in BUNDLE["benchmarks"].items():
            q = b["quantiles"]
            self.assertEqual(len(q), 101, name)
            self.assertTrue(all(x <= y for x, y in zip(q, q[1:])), name)
            self.assertEqual(set(b["stats"]), {"n", "mean", "p25", "p50", "p75", "p90"})
        real = BUNDLE["meta"]["real"]["titles"]
        self.assertEqual(BUNDLE["benchmarks"]["real-market"]["stats"]["n"], real["market"])
        self.assertEqual(BUNDLE["benchmarks"]["real-brands"]["stats"]["n"], real["brands"])
        self.assertEqual(BUNDLE["benchmarks"]["all"]["stats"]["n"], real["market"] + real["brands"])
        self.assertGreater(real["brands"], 50)

    def test_the_cohorts_have_names_in_both_languages(self):
        for c in ("real-market", "real-brands"):
            self.assertTrue(BUNDLE["cohort_labels"][c]["en"] and BUNDLE["cohort_labels"][c]["cs"])


class CardTests(unittest.TestCase):
    CARDS = BUNDLE["loot"]["cards"]

    def test_the_published_odds_and_the_pity_timer_are_kept(self):
        loot = BUNDLE["loot"]
        self.assertAlmostEqual(sum(loot["rates"].values()), 1.0)
        self.assertEqual(loot["pity_after"], 8)
        self.assertEqual(len({c["id"] for c in self.CARDS}), len(self.CARDS))
        self.assertEqual({c["rarity"] for c in self.CARDS}, {"common", "rare", "epic", "legendary"})

    def test_a_study_card_is_a_study_of_the_ledger_and_says_whether_it_is_verified(self):
        studies = {f"study-{s.id}": s for s in VERT.ledger().studies}
        cards = [c for c in self.CARDS if c["kind"] == "study"]
        self.assertEqual(len(cards), len(studies))
        for c in cards:
            s = studies[c["id"]]
            self.assertEqual(c["verified"], bool(s.verified))
            self.assertIn(s.title, c["body_cs"])
            self.assertIn("Zatím neověřeno" if not s.verified else "Ověřeno", c["body_cs"])
            self.assertTrue(c["body_en"] and c["title_en"] and c["title_cs"])

    def test_market_cards_repeat_numbers_that_can_be_counted_in_the_stored_results(self):
        by_id = {c["id"]: c for c in self.CARDS if c["kind"] == "market"}
        reach = RB.site_reach(RECORDS, A.load_config(ROOT / "radar", json.loads((VERT.path / "brands.json").read_text("utf-8"))))
        top = by_id["market-top-site"]
        self.assertIn(f"{reach[0].count} z {BUNDLE['meta']['real']['market_searches']}", top["body_cs"])
        self.assertIn(reach[0].name, top["title_cs"])
        self.assertEqual(len([c for c in by_id if c.startswith("market-") and c.split("-", 1)[1] in {f["id"] for f in BUNDLE["market"]["findings"]}]), len(BUNDLE["market"]["findings"]))
        for c in by_id.values():
            self.assertTrue(c["body_en"] and c["body_cs"])

    def test_there_are_tips_too(self):
        self.assertGreaterEqual(len([c for c in self.CARDS if c["kind"] == "tip"]), 5)


class ViewDataTests(unittest.TestCase):
    def test_tasks_come_from_the_radars_actions(self):
        tasks = BUNDLE["tasks"]
        actions = RB.R.report_data(SNAPSHOT, DRAFTS, PLAN)["actions"]
        self.assertEqual([t["id"] for t in tasks], [a["id"] for a in actions])
        self.assertEqual(len(tasks), 6)
        for t in tasks:
            self.assertEqual(t["xp"], RB.TASK_XP)
            self.assertTrue(t["title"] and t["why"] and t["steps"])

    def test_the_lab_has_the_ab_pairs_of_the_claim_bank(self):
        tests = BUNDLE["lab"]["tests"]
        bank = {c["id"]: c["text"] for c in BUNDLE["claimbank"]["claims"]}
        self.assertEqual(len(tests), len(BUNDLE["claimbank"]["tests"]))
        for t in tests:
            self.assertEqual((t["a"], t["b"]), (bank[t["a_id"]], bank[t["b_id"]]))
            self.assertTrue(t["hypothesis_cs"])

    def test_the_forge_shows_the_reviewed_drafts(self):
        packs = BUNDLE["forge_samples"]
        index = json.loads((DRAFTS / "index.json").read_text("utf-8"))
        self.assertEqual([p["draft"]["id"] for p in packs], [row["id"] for row in index])
        for p in packs:
            self.assertEqual(p["draft"]["errors"], 0)
            self.assertTrue(p["items"])

    def test_the_market_data_keeps_the_links_of_every_search(self):
        market = BUNDLE["market"]
        self.assertEqual(len(market["queries"]), len(RECORDS))
        self.assertEqual(sum(len(q["links"]) for q in market["queries"]), sum(len(r["links"]) for r in RECORDS))
        self.assertEqual(len(market["findings"]), 7)

    def test_the_claim_bank_passed_the_shield_with_nothing_to_report(self):
        t = BUNDLE["claimbank"]["totals"]
        self.assertEqual((t["errors"], t["warnings"]), (0, 0))


if __name__ == "__main__":
    unittest.main()
