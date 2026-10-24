"""The radar report page, the sentences behind it and the drafts it shows."""
import contextlib
import io
import json
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from dopamine_king import cli
from dopamine_king.generate.types import OfflineWriter
from dopamine_king.radar import compose as C
from dopamine_king.radar import drafts as D
from dopamine_king.radar import report as R
from dopamine_king.verticals import load_vertical

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "radar" / "snapshots" / "2026-10-23"
DRAFTS = ROOT / "radar" / "drafts" / "2026-10-23"
PLAN = ROOT / "radar" / "plan.json"
EM, EN = chr(0x2014), chr(0x2013)
DATA = R.report_data(SNAPSHOT, DRAFTS, PLAN)
PAGE = R.render_page(DATA)
NBSP = C.NBSP


class Anchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.hrefs, self.external, self.tags = set(), [], [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append(tag)
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "a" and a.get("href"):
            self.hrefs.append(a["href"])
            if a["href"].startswith("http"):
                self.external.append(a)
        if tag in ("script", "link", "img", "iframe", "form") and (a.get("src") or a.get("href")):
            self.external.append({"tag": tag, **a})


class ProseTests(unittest.TestCase):
    def test_czech_counts_and_lists(self):
        self.assertEqual([C.plural(n, "stránka", "stránky", "stránek") for n in (1, 2, 4, 5, 23)], ["stránka", "stránky", "stránky", "stránek", "stránek"])
        self.assertEqual(C.count(6, "stránku", "stránky", "stránek"), f"6{NBSP}stránek")
        self.assertEqual(C.names(["a", "b", "c"]), "a, b a c")
        self.assertEqual((C.pct(18, 54), C.pct(1, 0)), (33, 0))


class FindingTests(unittest.TestCase):
    def test_the_numbers_of_the_findings_are_the_numbers_of_the_analysis(self):
        by_id = {f["id"]: f for f in DATA["findings"]}
        v = DATA["visibility"]["all"]
        self.assertEqual(by_id["viditelnost"]["number"], f"{v['own']}{NBSP}z{NBSP}{v['queries']}")
        ident = DATA["identity"]
        self.assertEqual(by_id["identita"]["number"], f"{C.pct(ident['lookalike_links'], ident['counted_links'])}{NBSP}%")
        self.assertIn(f"{ident['lookalike_links']} z {ident['counted_links']} odkazů", by_id["identita"]["text"])
        audit = DATA["claims_audit"]
        self.assertEqual(by_id["trh-tvrzeni"]["number"], f"{audit['flagged']}{NBSP}z{NBSP}{audit['scanned']}")
        sci = DATA["science"]
        self.assertEqual(by_id["studie"]["number"], f"{sci['verified']}{NBSP}z{NBSP}{sci['total']}")
        self.assertIn(f"{sci['verified_now']} studií", by_id["studie"]["text"])
        top = DATA["landscape"]["domains"][0]
        self.assertIn(f"{top['name']} ({top['queries']}×)", by_id["trh"]["text"])

    def test_every_finding_has_a_caveat_and_evidence_that_exists(self):
        known = {q["id"] for q in DATA["queries"]} | {x["id"] for x in DATA["direct"]}
        self.assertGreaterEqual(len(DATA["findings"]), 6)
        for f in DATA["findings"]:
            self.assertTrue(f["caveat"] and f["title"] and f["text"], f["id"])
            self.assertTrue(f["evidence"] and set(f["evidence"]) <= known, f["id"])

    def test_every_action_belongs_to_a_finding_and_has_steps(self):
        ids = {f["id"] for f in DATA["findings"]}
        self.assertEqual(len({a["id"] for a in DATA["actions"]}), len(DATA["actions"]))
        for a in DATA["actions"]:
            self.assertIn(a["finding"], ids, a["id"])
            self.assertGreaterEqual(len(a["steps"]), 2, a["id"])

    def test_what_the_radar_cannot_see_is_listed_with_what_it_needs(self):
        self.assertGreaterEqual(len(DATA["open_items"]), 6)
        for item in DATA["open_items"]:
            self.assertTrue(item["what"] and item["why"] and item["need"])
        self.assertTrue(any("Network access" in i["need"] for i in DATA["open_items"]))


class PageTests(unittest.TestCase):
    def setUp(self):
        self.anchors = Anchors()
        self.anchors.feed(PAGE)

    def test_the_page_is_one_offline_file_with_no_long_dash(self):
        self.assertNotIn(EM, PAGE)
        self.assertNotIn(EN, PAGE)
        self.assertLess(len(PAGE.encode("utf-8")), 2_000_000)
        self.assertTrue(PAGE.startswith("<!doctype html>"))
        self.assertIn('<html lang="cs">', PAGE)
        self.assertIn("<title>MITO LIGHT Radar</title>", PAGE)
        self.assertIn("viewport-fit=cover", PAGE)
        scripts = [e for e in self.anchors.external if e.get("tag") == "script"]
        self.assertEqual(scripts, [])                                          # the only script is inline
        self.assertEqual([e for e in self.anchors.external if e.get("tag") in ("link", "img", "iframe", "form")], [])
        self.assertNotRegex(PAGE, r"(?:src|href)=[\"']http(?!s?://[^\"']+[\"'] target)")      # a web address is only ever a link that opens in a new tab

    def test_every_link_to_the_web_opens_in_a_new_tab_safely(self):
        self.assertGreater(len(self.anchors.external), 500)
        for a in self.anchors.external:
            self.assertEqual(a.get("target"), "_blank", a)
            self.assertIn("noopener", a.get("rel", ""), a)

    def test_every_anchor_points_to_an_element_of_the_page(self):
        for href in self.anchors.hrefs:
            if href.startswith("#"):
                self.assertIn(href[1:], self.anchors.ids, href)

    def test_findings_actions_drafts_and_all_searches_are_on_the_page(self):
        for f in DATA["findings"]:
            self.assertIn(R.esc(f["title"]), PAGE)
        for a in DATA["actions"]:
            self.assertIn(R.esc(a["title"]), PAGE)
        for x in DATA["drafts"]:
            self.assertIn(R.esc(x["title"]), PAGE)
        for q in DATA["queries"]:
            self.assertIn(f'id="q-{q["id"]}"', PAGE)
        self.assertEqual(PAGE.count('class="todo"'), len(DATA["actions"]))

    def test_the_headline_facts_are_computed(self):
        m = DATA["meta"]
        self.assertIn(f'{m["searches"]} skutečných hledání', PAGE)
        self.assertIn("0 simulovaných údajů", PAGE)
        self.assertEqual(m["searches"], len(DATA["queries"]))
        self.assertEqual(m["links"], sum(len(q["links"]) for q in DATA["queries"]))

    def test_the_claim_map_shows_every_topic_in_one_of_three_groups(self):
        for row in DATA["claim_map"]:
            self.assertIn(R.esc(row["name_cs"]), PAGE)
        for label in ("Můžete vysvětlovat", "Jen opatrně a se zdrojem", "Neříkejte"):
            self.assertIn(label, PAGE)

    def test_web_text_is_escaped(self):
        data = {"findings": [{"id": "x", "number": "1", "title": "<img src=x onerror=alert(1)>", "text": "<b>t</b>", "caveat": "c", "evidence": []}],
                "queries": [], "identity": {"quotes": []}}
        out = R.render_findings(data)
        self.assertNotIn("<img", out)
        self.assertNotIn("<b>t</b>", out)
        self.assertIn("&lt;img", out)
        self.assertIn("&lt;b&gt;t&lt;/b&gt;", out)

    def test_the_fragment_has_no_document_tags_and_keeps_the_page_contract(self):
        fragment = R.render_page(DATA, fragment=True)
        for tag in (r"<!doctype", r"<html[\s>]", r"<head[\s>]", r"<body[\s>]"):
            self.assertIsNone(re.search(tag, fragment.lower()), tag)
        self.assertTrue(fragment.lstrip().startswith('<meta name="claude:viewport-fit-sides" content="cover">'))
        self.assertIn("<title>MITO LIGHT Radar</title>", fragment[:400])
        self.assertIn('id="radar"', fragment)
        self.assertEqual(fragment.count("<style>"), 1)

    def test_colours_are_tokens_with_a_dark_variant(self):
        css = PAGE[PAGE.index("<style>"):PAGE.index("</style>")]
        self.assertIn("@media (prefers-color-scheme: dark) { :root:not([data-theme=\"light\"])", css)
        self.assertIn(':root[data-theme="dark"]', css)
        self.assertIn("background: var(--bg)", css)
        body_rules = css[css.index("\nbody {"):css.index("}", css.index("\nbody {"))]
        self.assertNotRegex(body_rules, r"#[0-9a-fA-F]{3,6}")


class ClaimsSectionTests(unittest.TestCase):
    E = DATA["emotion"]

    def setUp(self):
        self.anchors = Anchors()
        self.anchors.feed(PAGE)

    def test_the_section_is_in_the_navigation_and_the_header_points_to_it(self):
        self.assertIn('<section id="claimy">', PAGE)
        self.assertGreaterEqual(PAGE.count('href="#claimy"'), 2)            # the tab and the link in the header
        self.assertIn(f'Nově: emoční claimy, {C.count(self.E["totals"]["claims"], "hotová věta", "hotové věty", "hotových vět")}', PAGE)

    def test_every_claim_is_a_row_once_and_every_pick_a_card(self):
        for c in self.E["claims"]:
            self.assertEqual(PAGE.count(f'id="c-{c["id"]}"'), 1, c["id"])
            self.assertIn(R.esc(c["text"]), PAGE)
        for c in self.E["picks"]:
            self.assertEqual(PAGE.count(f'id="t-p-{c["id"]}"'), 1, c["id"])
        self.assertEqual(PAGE.count('class="pick"'), len(self.E["picks"]))

    def test_every_copy_button_points_to_text_on_the_page(self):
        targets = re.findall(r'data-target="([^"]+)"', PAGE)
        self.assertGreater(len(targets), len(self.E["claims"]))
        for target in targets:
            self.assertIn(target, self.anchors.ids, target)

    def test_a_sentence_the_shield_passed_has_no_flag_and_one_it_blocked_is_marked(self):
        self.assertEqual(R.verdict_pill({"verdict": {"errors": [], "warnings": []}}), "")
        stop = R.verdict_pill({"verdict": {"errors": ["CLAIM_MEDICAL"], "warnings": []}})
        self.assertIn("pill stop", stop)
        self.assertIn("zdravotní tvrzení", stop)
        self.assertIn("pill warn", R.verdict_pill({"verdict": {"errors": [], "warnings": ["OUTCOME_PROMISE"]}}))
        self.assertIn("Každá věta prošla kontrolou tvrzení bez chyby i varování.", PAGE)

    def test_the_page_says_why_the_word_dopamine_is_not_used_and_lists_the_studies(self):
        self.assertIn("Proč tu není slovo dopamin", PAGE)
        self.assertIn(R.esc(self.E["dopamine"]["summary"]), PAGE)
        for s in self.E["dopamine"]["studies"]:
            self.assertIn(R.esc(s["title"][:110]), PAGE)
        for c in self.E["claims"]:
            self.assertNotIn("dopamin", c["text"].lower())

    def test_the_forbidden_wordings_are_shown_with_what_the_shield_found(self):
        self.assertEqual(len(self.E["forbidden"]), PAGE.count('data-label="Neříkejte"'))
        for row in self.E["forbidden"]:
            self.assertTrue(row["found"], row["text"])
        self.assertNotIn("kontrola nezachytila", PAGE)

    def test_what_the_brand_must_confirm_is_on_the_page(self):
        self.assertIn("Než něco zveřejníte", PAGE)
        for n in self.E["needs"]:
            self.assertIn(R.esc(n["need"]), PAGE)

    def test_claim_text_is_escaped(self):
        uses = {"headline": "Nadpis: hlavní nadpis stránky"}
        row = R.claim_row({"id": "x", "use": "headline", "text": "<b>x</b>", "verdict": {"errors": [], "warnings": []}, "facts": [], "needs": "<i>y</i>"}, uses)
        self.assertNotIn("<b>x</b>", row)
        self.assertNotIn("<i>y</i>", row)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", row)

    def test_a_lever_row_names_the_strength_of_its_evidence(self):
        for lv in self.E["levers"]:
            self.assertIn(f'id="lever-{lv["id"]}"', PAGE)
            self.assertIn(R.LABEL_CS[lv["label"]], PAGE)


class BuildCommandTests(unittest.TestCase):
    def test_the_command_writes_the_page_and_a_fragment(self):
        with tempfile.TemporaryDirectory() as d:
            for name, extra in (("page.html", []), ("fragment.html", ["--fragment"])):
                out = Path(d) / name
                with contextlib.redirect_stdout(io.StringIO()) as buf:
                    code = cli.main(["radar", "build", "--snapshot", str(SNAPSHOT), "--drafts", str(DRAFTS), "--out", str(out), *extra])
                self.assertEqual(code, 0)
                self.assertIn(str(out), buf.getvalue())
            self.assertTrue((Path(d) / "page.html").read_text("utf-8").startswith("<!doctype html>"))
            self.assertFalse((Path(d) / "fragment.html").read_text("utf-8").startswith("<!doctype html>"))

    def test_the_committed_page_is_what_the_builder_makes(self):
        committed = (ROOT / "web" / "dist" / "mito-light-radar.html").read_text("utf-8")
        self.assertEqual(committed, PAGE, "rebuild with: python3 -m dopamine_king radar build --snapshot radar/snapshots/2026-10-23 --drafts radar/drafts/2026-10-23")


class DraftTests(unittest.TestCase):
    V = load_vertical("pbm")
    SPEC = json.loads((ROOT / "radar" / "drafts.json").read_text("utf-8"))

    def test_hook_counts_are_compared_with_the_numbered_points(self):
        self.assertEqual(D.count_mismatch("3 parametry, na které se podívat", "1) a\n2) b\n3) c\n4) d"), "Nadpis slibuje 3, text má očíslovaných bodů 4.")
        self.assertEqual(D.count_mismatch("3 parametry, na které se podívat", "1) a\n2) b\n3) c"), "")
        self.assertEqual(D.count_mismatch("pět praktických bodů", "1. a\n2. b\n3. c\n4. d"), "Nadpis slibuje 5, text má očíslovaných bodů 4.")
        self.assertEqual(D.count_mismatch("Jak vybrat panel", "1. a\n2. b"), "")
        self.assertEqual(D.count_mismatch("3 parametry", "bez očíslovaných bodů"), "")

    def test_one_job_per_page_and_one_per_persona_all_in_formal_czech(self):
        jobs = D.draft_jobs(self.V, self.SPEC, self.V.ledger())
        self.assertEqual([j["id"] for j in jobs], ["identita", "bezpecne-pouziti", "ozareni"] + [f"post-{p}" for p in self.SPEC["posts"]["personas"]])
        for job in jobs:
            self.assertEqual((job["brief"].address, job["brief"].lang, job["brief"].claims_profile), ("vy", "cs", "wellness"))
            self.assertTrue(job["brief"].facts, job["id"])
        pages = {j["id"]: j for j in jobs if j["kind"] == "page"}
        self.assertEqual(pages["identita"]["brief"].sources, [])                # no unrelated study on a page about the brand name
        self.assertTrue(pages["bezpecne-pouziti"]["brief"].sources)
        self.assertEqual(pages["ozareni"]["brief"].facts, self.SPEC["pages"][2]["facts"])
        self.assertEqual([j["id"] for j in D.draft_jobs(self.V, self.SPEC, self.V.ledger(), only={"ozareni"})], ["ozareni"])

    def test_the_facts_of_a_page_state_only_what_the_brand_file_supports(self):
        text = " ".join(f for page in self.SPEC["pages"] for f in page["facts"])
        self.assertNotIn(EM, text)
        self.assertNotIn(EN, text)
        for page in self.SPEC["pages"]:
            self.assertTrue(page["needs_approval"], page["id"])                  # the person who publishes sees what to confirm

    def test_a_run_writes_packs_and_an_index_and_a_partial_run_keeps_the_rest(self):
        ledger = self.V.ledger()
        with tempfile.TemporaryDirectory() as d:
            jobs = D.draft_jobs(self.V, self.SPEC, ledger, only={"post-fitness", "post-tech"})
            rows = D.run_jobs(jobs, OfflineWriter, ledger, d, workers=2, log=lambda line: None)
            self.assertEqual(sorted(r["id"] for r in rows), ["post-fitness", "post-tech"])
            self.assertTrue((Path(d) / "post-fitness" / "pack.json").exists())
            D.run_jobs(D.draft_jobs(self.V, self.SPEC, ledger, only={"post-tech"}), OfflineWriter, ledger, d, log=lambda line: None)
            index = json.loads((Path(d) / "index.json").read_text("utf-8"))
            self.assertEqual(sorted(r["id"] for r in index), ["post-fitness", "post-tech"])
            loaded = D.load_drafts(d)
            self.assertTrue(all(x["hook"] and x["body"] for x in loaded))
            self.assertTrue(all("issues" in x and "sources" in x for x in loaded))

    def test_the_committed_drafts_load_with_their_remarks(self):
        drafts = D.load_drafts(DRAFTS)
        self.assertEqual(len(drafts), 9)
        self.assertEqual({d["kind"] for d in drafts}, {"page", "post"})
        self.assertTrue(all(not re.search(r"\[\[cite:", d["body"]) for d in drafts))          # citation marks are numbers in the readable text
        self.assertTrue(all(EM not in d["body"] and EN not in d["body"] for d in drafts))


if __name__ == "__main__":
    unittest.main()
