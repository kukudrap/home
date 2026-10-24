"""The radar analysis: helpers, visibility, landscape, identity, themes, claims in titles, outcome titles, cross-check."""
import json
import tempfile
import unittest
from pathlib import Path

from dopamine_king.generate.claims import load_profile
from dopamine_king.radar import analyze as A
from dopamine_king.verticals import load_vertical

ROOT = Path(__file__).resolve().parent.parent
V = load_vertical("pbm")
PROFILE = load_profile("pbm", "wellness")
CLAIM_MAP = V.claim_map(V.ledger())
BRANDS = json.loads((V.path / "brands.json").read_text("utf-8"))
CFG = A.load_config(ROOT / "radar", BRANDS)
BRAND = {"name": "MITO LIGHT", "own_domains": ["mitolight.cz"], "related_domains": ["mitolight.com"], "aliases": ["mito light", "mitolight", "mitohacker"],
         "confusable": ["Mito Red Light", "mitoredlight.com"]}


def rec(id_, group, query, urls, *, domains=(), summary="", persona=""):
    links = [{"rank": i + 1, "title": t, "url": u} for i, (t, u) in enumerate(urls)]
    return {"id": id_, "group": group, "query": query, "allowed_domains": list(domains), "links": links, "summary": summary, "persona": persona, "purpose": ""}


class HelperTests(unittest.TestCase):
    def test_hosts_drop_www_and_match_subdomains(self):
        self.assertEqual(A.host_of("https://www.Drmax.cz/a?b=1"), "drmax.cz")
        self.assertTrue(A.host_matches("shop.mitolight.cz", ["mitolight.cz"]))
        self.assertFalse(A.host_matches("notmitolight.cz", ["mitolight.cz"]))

    def test_titles_that_say_nothing_are_junk_and_get_a_label_from_the_address(self):
        for title in ("Hlavní obsah", "dwn.alza.cz", "- 11 min read", "Table of Contents", "[Date Prev][Date Next]", "An image of a woman", "ab"):
            self.assertTrue(A.title_is_junk(title, "https://x.cz/"), title)
        self.assertFalse(A.title_is_junk("Červené světlo, jak funguje terapie lampou?", ""))
        shown = A.display({"title": "Hlavní obsah", "url": "https://www.seznamzpravy.cz/clanek/posvitte-si-cervene-265068"})
        self.assertEqual(shown, {"label": "posvitte si cervene 265068", "derived": True})
        self.assertEqual(A.display({"title": "Panel MITO LIGHT", "url": "https://x.cz/a"}), {"label": "Panel MITO LIGHT", "derived": False})

    def test_a_label_drops_leading_ids_and_extensions(self):
        self.assertEqual(A.slug_label("https://www.slevomat.cz/akce/2385920-terapie-cervenym-svetlem-1-3-nebo-5-navstev"), "terapie cervenym svetlem 1 3 nebo 5 navstev")
        self.assertEqual(A.slug_label("https://x.cz/manual_rl300_a2.pdf"), "manual rl300 a2")

    def test_light_related_text_is_recognised_with_and_without_diacritics(self):
        self.assertTrue(A.is_light_related("Červené světlo pro svaly"))
        self.assertTrue(A.is_light_related("Red light therapy panel"))
        self.assertFalse(A.is_light_related("Bolest kloubů - rizikové faktory a prevence"))


class ConfigTests(unittest.TestCase):
    def test_the_brand_registry_adds_makers_and_review_sites(self):
        info = A.domain_info("joovv.com", CFG["domains"])
        self.assertEqual(info["type"], "maker")
        self.assertEqual(A.domain_info("www.stackingyears.com".replace("www.", ""), CFG["domains"])["type"], "foreign_media")
        self.assertEqual(A.domain_info("pmc.example.drmax.cz", CFG["domains"])["type"], "pharmacy")      # a subdomain of a classified host
        self.assertEqual(A.domain_info("unknown.example", CFG["domains"]), {})

    def test_hand_made_entries_win_over_the_registry(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "domains.json").write_text(json.dumps({"types": {}, "domains": {"joovv.com": {"type": "noise", "name": "x"}}}), "utf-8")
            (root / "themes.json").write_text(json.dumps({"themes": []}), "utf-8")
            (root / "outcome_words.json").write_text(json.dumps({"words": []}), "utf-8")
            self.assertEqual(A.load_config(root, BRANDS)["domains"]["domains"]["joovv.com"]["type"], "noise")


class VisibilityTests(unittest.TestCase):
    RECORDS = [
        rec("brand-01", "brand", "MITO LIGHT", [("A", "https://mitoredlight.com/x"), ("B", "https://www.mitolight.cz/o-nas")]),
        rec("cat-01", "category", "terapie", [("Forbes", "https://forbes.cz/a"), ("Dr", "https://drmax.cz/b")]),
        rec("cat-02", "category", "panel", [("MITO", "https://mitolight.cz/p"), ("EU", "https://mitolight.com/q")]),
        rec("own-01", "own", "panel", [("MITO", "https://mitolight.cz/p")], domains=["mitolight.cz"]),
    ]

    def test_ranks_counts_and_look_alike_links(self):
        v = A.visibility(self.RECORDS, BRAND)
        rows = {r["id"]: r for r in v["rows"]}
        self.assertEqual((rows["brand-01"]["own_rank"], rows["brand-01"]["lookalike_links"]), (2, 1))
        self.assertEqual((rows["cat-01"]["own_rank"], rows["cat-01"]["top"]["host"]), (None, "forbes.cz"))
        self.assertEqual((rows["cat-02"]["own_rank"], rows["cat-02"]["other_market_rank"]), (1, 2))
        self.assertNotIn("own-01", rows)                                    # the site-only searches are not market visibility
        self.assertEqual(v["all"], {"queries": 3, "own": 2, "other_market": 1})
        self.assertEqual(v["market"], {"queries": 2, "own": 1})
        self.assertEqual(v["by_group"]["category"], {"queries": 2, "own": 1})


class LandscapeTests(unittest.TestCase):
    def test_classified_hosts_are_counted_per_query_and_noise_and_literature_are_set_aside(self):
        records = [
            rec("cat-01", "category", "a", [("x", "https://www.drmax.cz/a"), ("x", "https://drmax.cz/b"), ("x", "https://cz.rs-online.com/led"), ("x", "https://pubmed.ncbi.nlm.nih.gov/1"),
                                              ("x", "https://neznamy.example/z")]),
            rec("cat-02", "category", "b", [("x", "https://drmax.cz/c"), ("x", "https://forbes.cz/d")]),
            rec("brand-01", "brand", "c", [("x", "https://forbes.cz/e")]),                      # brand queries are not market queries
        ]
        out = A.landscape(records, CFG["domains"])
        self.assertEqual([(d["name"], d["queries"], d["links"]) for d in out["domains"]], [("Dr.Max", 2, 3), ("Forbes.cz", 1, 1)])
        self.assertEqual((out["noise_links"], out["unclassified_links"], out["links"]), (1, 1, 7))
        self.assertNotIn("science", {d["type"] for d in out["domains"]})


class IdentityTests(unittest.TestCase):
    def test_look_alike_share_third_party_pages_and_summary_sentences(self):
        records = [
            rec("brand-01", "brand", "MITO LIGHT", [("MITO LIGHT Europe Reviews", "https://ca.trustpilot.com/review/mitolight.com"), ("Find your panel", "https://mitoredlight.com/a"),
                                                   ("Reagent", "https://sigmaaldrich.com/p")],
                summary="Some text. Mito Red Light is a separate US brand that sells MITO LIGHT rivals. Other."),
            rec("brand-06", "brand", "Mito Light nebo Mito Red Light", [("x", "https://mitoredlight.com/b")]),
            rec("brand-02", "brand", "mitolight.cz", [("Více Mito Light produktu", "https://www.heureka.cz/znacky/mito-light/")]),
        ]
        direct = [{"id": "direct-06", "query": "q", "summary_sentence": "Značka MITO LIGHT je součástí širší skupiny Mito Red Light."}]
        out = A.identity(records, BRAND, CFG["domains"], direct)
        self.assertEqual((out["lookalike_links"], out["counted_links"]), (1, 4))                  # the comparison query is not counted
        self.assertEqual([a["host"] for a in out["about"]], ["ca.trustpilot.com", "heureka.cz"])
        self.assertEqual(out["worst"]["id"], "brand-01")
        self.assertEqual([q["id"] for q in out["quotes"]], ["brand-01", "direct-06"])
        self.assertTrue(all(q["machine_summary"] for q in out["quotes"]))


class ThemeTests(unittest.TestCase):
    def test_a_page_gets_the_themes_of_its_title_and_address(self):
        themes = CFG["themes"]
        self.assertEqual(A.theme_ids("How to Use a LED Device at Home", "https://x.com/how-to-use-an-led-device-at-home.html", themes), ["howto", "product"])
        self.assertIn("skin", A.theme_ids("How to Get Rid of Wrinkles", "https://x.com/blogs/editorial/how-to-get-rid-of-wrinkles", themes))
        self.assertIn("buying", A.theme_ids("Best red light panels 2026", "https://x.com/best", themes))
        self.assertEqual(A.theme_ids("Home", "https://x.com/", themes), [])

    def test_brand_sites_are_split_into_makers_and_media_and_other_domains_are_dropped(self):
        records = [
            rec("site-joovv", "brandsite", "q", [("Joovv Solo 3.0", "https://joovv.com/products/solo"), ("Paper", "https://biorxiv.org/x")], domains=["joovv.com"]),
            rec("site-lti", "brandsite", "q", [("Red Light Therapy Buyers Guide", "https://lighttherapyinsiders.com/buyers-guide/")], domains=["lighttherapyinsiders.com"]),
            rec("site-hooga", "brandsite", "q", [("Paper", "https://biorxiv.org/y")], domains=["hoogahealth.com"]),
        ]
        out = A.brandsites(records, CFG["themes"], CFG["domains"])
        self.assertEqual((out["pages"], out["sites_with_pages"], out["makers"], out["media"]), (2, 2, 2, 1))
        by_id = {t["id"]: t for t in out["themes"]}
        self.assertEqual(by_id["product"]["maker"], {"pages": 1, "sites": 1})
        self.assertEqual(by_id["buying"]["media"], {"pages": 1, "sites": 1})
        self.assertEqual([s["pages"] for s in out["sites"] if s["domain"] == "hoogahealth.com"], [[]])

    def test_the_own_pages_are_the_brand_domain_only_and_unique(self):
        records = [rec("own-01", "own", "q", [("Účinky červeného světla s vědeckými studiemi", "https://www.mitolight.cz/ucinky-a-studie/"), ("Paper", "https://biorxiv.org/x")]),
                   rec("own-02", "own", "q", [("Účinky červeného světla s vědeckými studiemi", "https://mitolight.cz/ucinky-a-studie")])]
        own = A.own_pages(records, BRAND, CFG["themes"])
        self.assertEqual(len(own["pages"]), 1)
        self.assertIn("science", own["themes"])


class ClaimTests(unittest.TestCase):
    RECORDS = [
        rec("site-welzo", "brandsite", "q", [("Welzo ProMax Clinical Grade Portable Red Light Panel", "https://welzo.com/p"), ("Is Red Light Therapy Safe for Eyes?", "https://welzo.com/q"),
                                             ("Hlavní obsah", "https://welzo.com/r"), ("Panel s červeným světlem pro regeneraci", "https://welzo.com/s")]),
        rec("cat-01", "category", "q", [("Clinical-Grade Red Light Therapy Panel", "https://mitolight.cz/x"), ("Laser pain therapy patent", "https://image-ppubs.uspto.gov/1"),
                                        ("Red Light Therapy for Back Pain", "https://redlighttherapy.expert/back")]),
        rec("study-01", "study", "q", [("Red light cures everything", "https://welzo.com/t")]),
    ]

    def test_only_selling_hosts_light_titles_and_statements_are_checked(self):
        out = A.claims_audit(self.RECORDS, PROFILE, CFG["domains"], own_domains=["mitolight.cz"])
        self.assertEqual(out["scanned"], 3)                          # the question, the junk title, the patent host, the own site and the study search are out
        self.assertEqual([(e["name"], e["code"]) for e in out["examples"]], [("Welzo", "STATUS_CLAIM"), ("Red Light Therapy Expert", "CLAIM_MEDICAL")])
        self.assertEqual(out["flagged"], 2)
        self.assertEqual(out["by_rule"], {"tvrzení o regulačním statusu": 1, "zdravotní tvrzení (léčí, zmírňuje)": 1})
        self.assertEqual(out["examples"][0]["fragment"], "Clinical Grade")

    def test_a_title_with_a_topic_and_an_outcome_word_is_listed_for_review(self):
        pages = [{"url": "https://x.cz/1", "label": "Červené světlo proti vráskám"}, {"url": "https://x.cz/2", "label": "Zvýšení kvality a množství vlasů díky fotobiomodulaci"},
                 {"url": "https://x.cz/3", "label": "Často kladené otázky"}, {"url": "https://x.cz/4", "label": "Kvalitnější spánek s červeným světlem"},
                 {"url": "https://x.cz/5", "label": "Panel MITO LIGHT Expert 5.0"}]
        rows = A.outcome_titles(pages, PROFILE, CLAIM_MAP, CFG["outcome"])
        self.assertEqual([(r["topic_id"], r["class"]) for r in rows], [("pbm-skin-appearance", "cosmetic"), ("pbm-hair", "medical"), ("pbm-sleep", "wellness")])
        self.assertTrue(all(r["safe"] for r in rows))


class ValidationTests(unittest.TestCase):
    def test_overlap_and_order_against_a_direct_search(self):
        stored = [rec("cat-01", "category", "q", [("a", "https://a.cz/1"), ("b", "https://b.cz/2"), ("c", "https://c.cz/3")])]
        direct = [{"id": "direct-01", "query": "q", "compare_with": "cat-01", "links": [{"url": "https://a.cz/1"}, {"url": "https://b.cz/2"}, {"url": "https://d.cz/4"}]},
                  {"id": "direct-02", "query": "q", "compare_with": "", "links": []}]
        self.assertEqual(A.validation(stored, direct), [{"direct": "direct-01", "query": "q", "stored": 3, "direct_links": 3, "shared": 2, "same_order": False}])


if __name__ == "__main__":
    unittest.main()
