import json
import re
import unittest

from dopamine_king.generate import seo
from dopamine_king.generate.types import Brief, Draft, OfflineWriter

SOURCES = [
    {"id": "s1", "title": "Footwear fit study", "url": "https://example.org/study", "claim": "Fit matters for injury risk"},
    {"id": "s2", "title": "Runner guide", "url": "https://example.org/guide", "claim": "Replace shoes regularly"},
    {"id": "s3", "title": "Gait survey", "url": "https://example.org/survey", "claim": "Most beginners skip a gait check"},
]
FACT = "In our 2025 gait lab, 38% of 412 beginner runners picked shoes that did not match their foot type."
EN = Brief(brand="Zorvia", topic="running shoes", audience="beginner runners", keyword="running shoes for flat feet",
           cta="Take the 2-minute fit quiz", facts=[FACT, "Our fit quiz takes two minutes."], sources=SOURCES)
CS = Brief(brand="Zorvia", topic="běžecké boty", audience="začínající běžci", lang="cs", keyword="běžecké boty",
           cta="Vyzkoušejte test", facts=["V našem testu jsme v roce 2025 měřili 412 běžců."], sources=SOURCES,
           topic_forms={"gen": "běžeckých bot", "loc": "běžeckých botách", "acc": "běžecké boty", "dat": "běžeckým botám",
                        "ins": "běžeckými botami"})
CS_PLAIN = Brief(brand="Zorvia", topic="marketingová automatizace", audience="malé firmy", lang="cs")
BARE_EN = Brief(brand="Acme", topic="project management software", audience="small teams")

SENTENCES = [
    "Flat feet change how the arch absorbs impact, so the right shoe needs stable support.",
    "Most beginners pick shoes by colour and price, then wonder why their knees hurt.",
    "A short gait check at a specialist store takes ten minutes and costs nothing.",
    "Try shoes in the afternoon because feet swell during the day.",
    "Leave a thumb width of space in front of the longest toe.",
    "Replace the pair when the midsole feels flat or the outsole is worn smooth.",
    "Rotate two pairs if you run more than three times a week.",
    "Walk, jog a few steps and check for heel slip before you buy.",
    "Keep a simple log with distance, pace and any pain you notice.",
    "Stop and ask a coach when pain lasts longer than a few days.",
]


def prose(n_words: int, offset: int = 0) -> str:
    out, count, i = [], 0, offset
    while count < n_words:
        s = SENTENCES[i % len(SENTENCES)]
        out.append(s)
        count += len(s.split())
        i += 1
    return " ".join(out)


SENTENCES_CS = [
    "Při plochých chodidlech klenba hůře tlumí nárazy, proto je potřeba stabilní podpora.",
    "Začátečníci často vybírají podle barvy a ceny a pak se divní, že je bolí kolena.",
    "Krátké vyšetření chůze v odborné prodejně trvá deset minut a nic nestojí.",
    "Zkoušejte obuv odpoledne, protože chodidla přes den otékají.",
    "Před špičkou nechte volné místo široké jako palec.",
    "Pár vyměňte, když je střední část podrážky ztvrdlá nebo je vnější podrážka zničená.",
    "Pokud běháte častěji než třikrát týdně, střídejte dva páry.",
    "Před koupí si projděte pár kroků, zaběhněte si a zkontrolujte, zda pata neprokluzuje.",
    "Veďte si jednoduchý deník se vzdáleností, tempem a případnou bolestí.",
    "Když bolest trvá déle než pár dní, zeptejte se trenéra.",
]


def prose_cs(n_words: int, offset: int = 0) -> str:
    out, count, i = [], 0, offset
    while count < n_words:
        s = SENTENCES_CS[i % len(SENTENCES_CS)]
        out.append(s)
        count += len(s.split())
        i += 1
    return " ".join(out)


def filled_article(brief=EN, **options):
    """A fully written article: every open slot gets generated prose, one section cites a source."""
    opts = {"word_target": 650, "sections": 3, "published": "2026-09-30", "author": {"name": "Jana Novak", "role": "running coach"},
            "internal_links": [{"url": "/a", "anchor": "Shoe guide"}, {"url": "/b", "anchor": "Gait check"}, {"url": "/c", "anchor": "Fit quiz"}]}
    opts.update(options)
    sk = seo.build_seo_article(brief, options=opts)
    fills = OfflineWriter().fill(sk, brief)
    for i, slot in enumerate(sk.slots):
        if slot.id in fills:
            continue
        gen, lead = (prose_cs, " potřebují pevnou oporu klenby a stabilní patu. ") if brief.lang == "cs" else (prose, " need firm arch support and a stable heel. ")
        if slot.id == "answer_lead":
            fills[slot.id] = seo.cap_first(brief.primary_keyword) + lead + gen(30)
        else:
            fills[slot.id] = gen(max(20, (slot.max_words or 60) * 2 // 3), i)
    fills["sec_1"] += " The fit study backs this up [[cite:s1]]."
    return sk, sk.render(fills)


def mk_draft(body, lang="en", keyword="running shoes", **parts):
    return Draft(format="seo_article", lang=lang, hook="", body=body, parts=parts, meta={"keyword": keyword})


class SlugifyTests(unittest.TestCase):
    def test_czech_diacritics_and_hyphens(self):
        self.assertEqual(seo.slugify("Běžecké boty: jak vybrat?", "cs"), "bezecke-boty-jak-vybrat")
        self.assertEqual(seo.slugify("Žluťoučký kůň úpěl ďábelské ódy", "cs"), "zlutoucky-kun-upel-dabelske-ody")

    def test_lowercase_symbols_and_trim(self):
        self.assertEqual(seo.slugify("  --Hello,   WORLD!!  "), "hello-world")
        self.assertEqual(seo.slugify("C++ & Rust"), "c-and-rust")
        self.assertEqual(seo.slugify("Tipy & triky", "cs"), "tipy-a-triky")
        self.assertEqual(seo.slugify("Straße"), "strasse")
        self.assertEqual(seo.slugify("???"), "")

    def test_max_len_cuts_at_word_boundary(self):
        slug = seo.slugify("running shoes for flat feet the long guide to picking a pair you will love", max_len=30)
        self.assertLessEqual(len(slug), 30)
        self.assertFalse(slug.endswith("-"))
        self.assertTrue("running-shoes-for-flat-feet-the-long-guide".startswith(slug))


class IntentTests(unittest.TestCase):
    def test_english(self):
        cases = {"how to choose running shoes": "informational", "what is a gait check": "informational",
                 "best running shoes": "commercial", "nike vs adidas running shoes": "commercial",
                 "buy running shoes online": "transactional", "running shoes price": "transactional",
                 "zorvia login": "navigational", "running shoes": "informational", "": "informational"}
        for kw, intent in cases.items():
            self.assertEqual(seo.detect_intent(kw, "en"), intent, kw)

    def test_czech(self):
        cases = {"jak vybrat běžecké boty": "informational", "co je marketingová automatizace": "informational",
                 "nejlepší běžecké boty": "commercial", "běžecké boty srovnání": "commercial", "recenze běžeckých bot": "commercial",
                 "koupit běžecké boty": "transactional", "cena běžeckých bot": "transactional", "běžecké boty": "informational",
                 "zorvia přihlášení": "navigational"}
        for kw, intent in cases.items():
            self.assertEqual(seo.detect_intent(kw, "cs"), intent, kw)

    def test_works_without_diacritics_and_mixed_language(self):
        self.assertEqual(seo.detect_intent("nejlepsi bezecke boty", "cs"), "commercial")
        self.assertEqual(seo.detect_intent("best bezecke boty", "cs"), "commercial")

    def test_how_to_beats_a_weaker_commercial_cue(self):
        self.assertEqual(seo.detect_intent("how to choose the best running shoes"), "informational")
        self.assertEqual(seo.detect_intent("what is the best running shoe"), "commercial")


class JsonLdTests(unittest.TestCase):
    def test_article_structure_and_clean_values(self):
        node = seo.jsonld_article("A" * 200, description="[[ADD: later]]", url="https://x.org/a", lang="cs",
                                  author={"name": "Jana", "role": "coach"}, publisher="Zorvia", published="2026-09-30", keywords=["k1", "k2"])
        self.assertEqual((node["@context"], node["@type"]), ("https://schema.org", "Article"))
        self.assertEqual(len(node["headline"]), 110)
        self.assertNotIn("description", node)                      # placeholders never reach the markup
        self.assertEqual(node["author"], {"@type": "Person", "name": "Jana", "jobTitle": "coach"})
        self.assertEqual(node["mainEntityOfPage"]["@id"], "https://x.org/a")
        self.assertEqual(node["keywords"], "k1, k2")
        self.assertEqual(node["inLanguage"], "cs")
        self.assertNotIn("image", node)

    def test_faq_skips_unfilled_pairs_and_strips_markers(self):
        node = seo.jsonld_faq([("Q1?", "Answer [[cite:s1]] with [link](https://x.org)."), ("Q2?", ""), ("", "A"), ("Q3?", "[[ADD: x]]"), {"q": "Q4?", "a": "Four"}])
        self.assertEqual(node["@type"], "FAQPage")
        self.assertEqual([e["name"] for e in node["mainEntity"]], ["Q1?", "Q4?"])
        self.assertEqual(node["mainEntity"][0]["acceptedAnswer"]["text"], "Answer with link.")
        self.assertEqual(seo.jsonld_faq([])["mainEntity"], [])

    def test_howto_positions_and_options(self):
        node = seo.jsonld_howto("Fit shoes", ["Measure", {"name": "Walk", "text": "Walk 10 steps"}, ""], total_time="PT15M", tools=["Ruler"])
        self.assertEqual(node["@type"], "HowTo")
        self.assertEqual([s["position"] for s in node["step"]], [1, 2])
        self.assertEqual(node["step"][1]["name"], "Walk")
        self.assertEqual(node["totalTime"], "PT15M")
        self.assertEqual(node["tool"][0]["@type"], "HowToTool")

    def test_video_organization_and_breadcrumbs(self):
        video = seo.jsonld_video("Demo", "A demo", thumbnail_url="https://x.org/t.jpg", upload_date="2026-01-01", duration="PT2M")
        self.assertEqual((video["@type"], video["uploadDate"], video["duration"]), ("VideoObject", "2026-01-01", "PT2M"))
        org = seo.jsonld_organization("Zorvia", url="https://zorvia.com", same_as=["https://x.com/zorvia"])
        self.assertEqual((org["@type"], org["sameAs"]), ("Organization", ["https://x.com/zorvia"]))
        crumbs = seo.jsonld_breadcrumbs([("Home", "https://z.com"), {"name": "Blog", "url": "https://z.com/blog"}, ("Post",)])
        self.assertEqual([c["position"] for c in crumbs["itemListElement"]], [1, 2, 3])
        self.assertNotIn("item", crumbs["itemListElement"][2])

    def test_render_is_valid_json_and_safe_in_a_script_tag(self):
        node = seo.jsonld_faq([("Why </script> tags?", "Because.")])
        html = seo.render_jsonld([node, seo.jsonld_organization("Z")])
        self.assertEqual(html.count('<script type="application/ld+json">'), 2)
        self.assertNotIn("</script> tags", html)
        body = html.split("\n", 1)[1].rsplit("</script>", 1)[0]
        self.assertTrue(body)
        first = html.split("</script>")[0].split("\n", 1)[1]
        self.assertEqual(json.loads(first.replace("<\\/", "</"))["@type"], "FAQPage")


class BuilderTests(unittest.TestCase):
    def test_skeleton_structure_and_meta(self):
        sk = seo.build_seo_article(EN)
        ids = [s.id for s in sk.slots]
        for needed in ("title", "meta_description", "h1", "answer_lead", "experience", "sec_1", "sec_6", "faq_q1", "faq_a4",
                       "conclusion", "cta", "author_box"):
            self.assertIn(needed, ids)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sk.format, "seo_article")
        self.assertEqual(sk.hook_slot, "title")
        for key in ("goal", "cta", "sponsored", "keyword", "lang"):
            self.assertIn(key, sk.meta)
        self.assertEqual(sk.meta["keyword"], "running shoes for flat feet")
        self.assertEqual(sk.slot("answer_lead").max_words, 60)
        self.assertEqual(sk.slot("title").max_chars, 60)
        for sid in re.findall(r"\{\{([a-z0-9_]+)\}\}", sk.template):
            self.assertIn(sid, ids)

    def test_titles_fit_and_contain_the_keyword(self):
        for kw in ("running shoes", "running shoes for flat feet", "how to choose running shoes", "best running shoes", "buy running shoes online",
                   "ergonomic standing desk converters for small home offices"):
            b = Brief(brand="Zorvia", topic="running shoes", audience="beginner runners", keyword=kw)
            title = seo.build_seo_article(b).slot("title").default
            self.assertLessEqual(len(title), 60, title)
            if len(kw) < 45:
                self.assertTrue(seo.count_keyword(title, kw) >= 1, (kw, title))

    def test_czech_titles_fit_and_contain_the_keyword(self):
        for kw in ("běžecké boty", "nejlepší běžecké boty", "koupit běžecké boty", "jak vybrat běžecké boty"):
            b = Brief(brand="Zorvia", topic="běžecké boty", audience="začínající běžci", lang="cs", keyword=kw)
            title = seo.build_seo_article(b).slot("title").default
            self.assertLessEqual(len(title), 60, title)
            self.assertGreaterEqual(seo.count_keyword(title, kw, "cs"), 1, title)

    def test_meta_description_default_is_fitted_and_has_the_keyword(self):
        for brief in (EN, CS, CS_PLAIN, BARE_EN):
            for intent in ("informational", "commercial", "transactional"):
                sk = seo.build_seo_article(brief, options={"intent": intent})
                meta = sk.slot("meta_description").default
                self.assertTrue(120 <= len(meta) <= 155, (brief.brand, intent, len(meta), meta))
                self.assertGreaterEqual(seo.count_keyword(meta, brief.primary_keyword, brief.lang), 1, meta)

    def test_at_least_half_of_the_h2_are_questions(self):
        for brief in (EN, CS, CS_PLAIN):
            for intent in ("informational", "commercial", "transactional"):
                for n in (3, 6, 8):
                    d = seo.build_seo_article(brief, options={"intent": intent, "sections": n}).render()
                    h2 = [t for lv, t in seo.parse_headings(d.body) if lv == 2]
                    ratio = sum(t.endswith("?") for t in h2) / len(h2)
                    self.assertGreaterEqual(ratio, 0.5, (brief.lang, intent, n, h2))
                    self.assertEqual(d.parts["outline"], h2)
                    self.assertAlmostEqual(d.parts["question_ratio"], round(ratio, 3), places=3)

    def test_outline_depends_on_intent(self):
        info = seo.build_seo_article(EN, options={"intent": "informational"}).fixed["headings"]
        comm = seo.build_seo_article(EN, options={"intent": "commercial"}).fixed["headings"]
        trans = seo.build_seo_article(EN, options={"intent": "transactional"}).fixed["headings"]
        self.assertEqual(len(info), 6)
        self.assertIn("What do we mean by running shoes for flat feet?", info)
        self.assertTrue(any("mistakes" in h for h in info))
        self.assertTrue(any("compare" in h for h in comm) and any("pros and cons" in h for h in comm) and any("pay" in h for h in comm))
        self.assertTrue(any("order" in h for h in trans) and any("benefits" in h for h in trans) and any("evidence" in h for h in trans))
        self.assertNotEqual(info, comm)
        self.assertEqual(seo.build_seo_article(EN, options={"sections": 99}).fixed["headings"].__len__(), 8)
        self.assertEqual(len(seo.build_seo_article(EN, options={"sections": 1}).fixed["headings"]), 3)

    def test_intent_is_detected_from_the_keyword(self):
        self.assertEqual(seo.build_seo_article(Brief(brand="B", topic="t", audience="a", keyword="best running shoes")).fixed["intent"], "commercial")
        self.assertEqual(seo.build_seo_article(Brief(brand="B", topic="t", audience="a", keyword="zorvia login")).fixed["intent"], "navigational")
        self.assertIn("Navigational", " ".join(seo.build_seo_article(Brief(brand="B", topic="t", audience="a", keyword="zorvia login")).notes))

    def test_offline_render_shows_placeholders_for_prose_and_fills_experience_from_facts(self):
        sk = seo.build_seo_article(EN)
        d = sk.render(OfflineWriter().fill(sk, EN))
        self.assertEqual(d.parts["slots"]["experience"], FACT)
        self.assertIn(f"> **From our own experience:** {FACT}", d.body)
        expected_open = ["answer_lead"] + [f"sec_{i}" for i in range(1, 7)] + [f"faq_a{i}" for i in range(1, 5)] + ["conclusion", "author_box"]
        self.assertEqual(d.slots_open, expected_open)
        self.assertIn("[[ADD: Answer-first paragraph", d.body)
        self.assertEqual(d.parts["slots"]["cta"], "Take the 2-minute fit quiz")
        self.assertEqual(d.hook, d.parts["slots"]["title"])

    def test_experience_is_open_without_facts_and_never_invented(self):
        sk = seo.build_seo_article(BARE_EN)
        self.assertIsNone(sk.slot("experience").default)
        self.assertIsNone(sk.slot("cta").default)
        d = sk.render(OfflineWriter().fill(sk, BARE_EN))
        self.assertIn("experience", d.slots_open)
        self.assertIn("[[ADD: First-party experience (required)", d.body)
        self.assertNotIn("Sources", d.body)

    def test_no_default_for_any_prose_that_needs_real_content(self):
        sk = seo.build_seo_article(EN)
        for slot in sk.slots:
            if slot.id.startswith(("sec_", "faq_a")) or slot.id in ("answer_lead", "conclusion"):
                self.assertIsNone(slot.default, slot.id)

    def test_sources_block_is_numbered_from_vetted_sources_only(self):
        d = seo.build_seo_article(EN).render()
        self.assertIn("## Sources\n\n1. [Footwear fit study](https://example.org/study)\n2. [Runner guide](https://example.org/guide)\n3. [Gait survey]", d.body)
        self.assertEqual([s["id"] for s in d.parts["sources"]], ["s1", "s2", "s3"])
        self.assertIn("Vetted sources: s1 (Fit matters for injury risk)", d.body)
        self.assertEqual(seo.render_citations("Fit matters [[cite:s2]] and [[cite:zzz]].", SOURCES), "Fit matters [2] and [[cite:zzz]].")

    def test_internal_links_author_published_and_options(self):
        opts = {"published": "2026-09-30", "author": {"name": "Jana Novak", "role": "running coach"},
                "internal_links": [{"url": "/guide", "anchor": "Shoe guide"}, {"url": ""}, {"anchor": "no url"}], "word_target": 900}
        sk = seo.build_seo_article(EN, options=opts)
        d = sk.render(OfflineWriter().fill(sk, EN))
        self.assertEqual(d.parts["internal_links"], [{"url": "/guide", "anchor": "Shoe guide"}])
        self.assertIn("**Related reading:**\n\n- [Shoe guide](/guide)", d.body)
        self.assertIn("*Published: September 30, 2026*", d.body)
        self.assertEqual(d.parts["slots"]["author_box"], "Jana Novak, running coach, Zorvia")
        self.assertEqual(d.parts["word_target"], 900)
        self.assertEqual(d.parts["json_ld"][0]["datePublished"], "2026-09-30")
        self.assertEqual(d.parts["json_ld"][0]["author"]["jobTitle"], "running coach")

    def test_word_budget_scales_with_the_target(self):
        small = seo.build_seo_article(EN, options={"word_target": 800}).slot("sec_1").max_words
        big = seo.build_seo_article(EN, options={"word_target": 3000}).slot("sec_1").max_words
        self.assertLess(small, big)
        self.assertRegex(seo.build_seo_article(EN, options={"word_target": 3000}).slot("sec_1").instruction, r"Write \d+-\d+ words")

    def test_hook_becomes_the_title_when_it_fits_else_the_h1(self):
        sk = seo.build_seo_article(EN, hook="Running shoes for flat feet: 5 fit checks")
        self.assertEqual(sk.slot("title").default, "Running shoes for flat feet: 5 fit checks")
        self.assertEqual(sk.slot("h1").default, "Running shoes for flat feet: 5 fit checks")
        long_hook = "Why every beginner runner with flat feet gets the shoe choice wrong"
        sk = seo.build_seo_article(EN, hook=long_hook)
        self.assertNotEqual(sk.slot("title").default, long_hook)
        self.assertEqual(sk.slot("h1").default, long_hook)

    def test_czech_builder_uses_diacritics_and_never_leaks_format_fields(self):
        for brief in (CS, CS_PLAIN):
            d = seo.build_seo_article(brief).render(OfflineWriter().fill(seo.build_seo_article(brief), brief))
            self.assertIn("Časté dotazy", d.body)
            self.assertIn("Závěr", d.body)
            self.assertNotRegex(d.body.replace("{{", ""), r"\{[a-zA-Z]+\}")
            self.assertNotIn(chr(0x2014), d.body)
            self.assertTrue(d.parts["slots"]["title"].startswith(seo.cap_first(brief.primary_keyword.split()[0])[:3]))

    def test_czech_case_forms_are_used_only_when_known(self):
        with_forms = seo.build_seo_article(CS).render()
        without = seo.build_seo_article(Brief(**{**CS.to_dict(), "topic_forms": {}})).render()
        self.assertIn("o běžeckých botách", with_forms.parts["slots"]["faq_q1"])
        self.assertNotIn("botách", without.parts["slots"]["faq_q1"])
        self.assertEqual(without.parts["slots"]["faq_q1"], "Běžecké boty: co je dobré vědět na začátku?")

    def test_json_ld_is_built_from_filled_values(self):
        sk = seo.build_seo_article(EN)
        d = sk.render({"faq_a1": "Pick a stable shoe.", "faq_a3": "Skipping the fit check.", "meta_description": ""})
        types = [n["@type"] for n in d.parts["json_ld"]]
        self.assertEqual(types, ["Article", "FAQPage"])
        faq = d.parts["json_ld"][1]["mainEntity"]
        self.assertEqual(len(faq), 2)
        self.assertEqual(faq[0]["acceptedAnswer"]["text"], "Pick a stable shoe.")
        self.assertNotIn("[[ADD", json.dumps(d.parts["json_ld"]))
        self.assertEqual(d.parts["slug"], seo.slugify(d.parts["slots"]["title"]))
        empty = sk.render()
        self.assertEqual([n["@type"] for n in empty.parts["json_ld"]], ["Article"])

    def test_toc_and_outline(self):
        d = seo.build_seo_article(EN).render()
        self.assertEqual(len(d.parts["toc"]), len(d.parts["outline"]))
        self.assertEqual(d.parts["toc"][0]["anchor"], seo.slugify(d.parts["outline"][0]))
        self.assertEqual(d.parts["outline"][-3:], ["Frequently asked questions", "Conclusion", "Sources"])

def check(report, cid):
    return next(c for c in report.checks if c.id == cid)


def article_body(title="Running shoes: a practical guide", meta=None, intro=None, extra="", faq=3, h1=1, cites=2, kw_hits=6):
    """A crafted Markdown article with controllable defects."""
    meta = meta if meta is not None else "Running shoes for beginners: how to pick, fit and replace a pair without wasting money or hurting your knees, with a checklist."
    intro = intro if intro is not None else "Running shoes need firm support. " + prose(40)
    lines = ["---", f"title: {title}", f"description: {meta}", "---", ""]
    lines += ["# Running shoes: a practical guide"] * h1 + ["", intro, ""]
    for i in range(3):
        lines += [f"## Section {i}?", "", prose(60, i) + (" Running shoes matter here." if i < kw_hits else ""), ""]
    lines += ["## FAQ", ""]
    for i in range(faq):
        lines += [f"### Question {i}?", "", prose(20, i), ""]
    lines += [extra, "", "## Sources", ""] + [f"{i + 1}. [Source {i}](https://example.org/s{i})" for i in range(cites)]
    return "\n".join(lines)


class SeoScoreTests(unittest.TestCase):
    def test_good_draft_passes_every_check(self):
        _, d = filled_article()
        r = seo.seo_score(d, EN)
        self.assertEqual([c.id for c in r.checks if not c.passed], [])
        self.assertGreaterEqual(r.score, 99)
        self.assertEqual(r.penalty, 0.0)
        self.assertEqual(len(r.checks), 12)
        self.assertAlmostEqual(sum(c.weight for c in r.checks), 1.0)
        self.assertEqual(r.issues, [])

    def test_good_czech_draft_scores_high_and_messages_are_czech(self):
        _, d = filled_article(CS)
        r = seo.seo_score(d, CS)
        self.assertEqual([c.id for c in r.checks if not c.passed], [])
        self.assertGreaterEqual(r.score, 99)
        self.assertEqual(d.lang, "cs")
        self.assertTrue(check(r, "title").message.startswith("Délka titulku"))
        self.assertIn("Hustota klíčového slova", check(r, "keyword_density").message)

    def test_bad_draft_scores_low(self):
        body = "# Running shoes\n\n# Again running shoes\n\n### Skipped level\n\nShort text.\n\n### Skipped level\n\nMore."
        r = seo.seo_score(mk_draft(body))
        failed = {c.id for c in r.checks if not c.passed}
        self.assertTrue({"single_h1", "heading_hierarchy", "faq", "sources", "word_count", "unique_headings", "meta_description"} <= failed)
        self.assertLess(r.score, 45)
        codes = {i.code for i in r.issues}
        self.assertIn("H1_COUNT", codes)
        self.assertIn("SOURCES_MISSING", codes)
        self.assertEqual({i.severity for i in r.issues if i.code == "H1_COUNT"}, {"error"})

    def test_title_check(self):
        ok = seo.seo_score(mk_draft(article_body()))
        self.assertTrue(check(ok, "title").passed)
        long = seo.seo_score(mk_draft(article_body(title="Running shoes: " + "x" * 60)))
        self.assertFalse(check(long, "title").passed)
        nokw = seo.seo_score(mk_draft(article_body(title="A practical guide")))
        self.assertFalse(check(nokw, "title").passed)
        self.assertIn("missing", check(nokw, "title").message)

    def test_meta_description_check(self):
        self.assertTrue(check(seo.seo_score(mk_draft(article_body())), "meta_description").passed)
        self.assertFalse(check(seo.seo_score(mk_draft(article_body(meta="Running shoes guide."))), "meta_description").passed)
        no_kw = "A practical guide for beginners: how to pick, fit and replace a pair without wasting money or hurting your knees at all."
        self.assertFalse(check(seo.seo_score(mk_draft(article_body(meta=no_kw))), "meta_description").passed)

    def test_h1_and_hierarchy_and_duplicate_headings(self):
        self.assertFalse(check(seo.seo_score(mk_draft(article_body(h1=2))), "single_h1").passed)
        self.assertFalse(check(seo.seo_score(mk_draft(article_body(h1=0))), "single_h1").passed)
        self.assertTrue(check(seo.seo_score(mk_draft(article_body())), "heading_hierarchy").passed)
        self.assertFalse(check(seo.seo_score(mk_draft("# T\n\n### Skip\n\ntext")), "heading_hierarchy").passed)
        self.assertFalse(check(seo.seo_score(mk_draft("## Starts at two\n\ntext")), "heading_hierarchy").passed)
        dup = article_body() + "\n\n## Section 0?\n\nagain"
        self.assertFalse(check(seo.seo_score(mk_draft(dup)), "unique_headings").passed)

    def test_keyword_in_first_100_words(self):
        late = article_body(intro=prose(120) + " Running shoes appear late.")
        self.assertFalse(check(seo.seo_score(mk_draft(late)), "keyword_early").passed)
        self.assertTrue(check(seo.seo_score(mk_draft(article_body())), "keyword_early").passed)

    def test_keyword_density_and_stuffing_penalty(self):
        low = seo.seo_score(mk_draft(article_body(kw_hits=0).replace("Running shoes need", "Footwear needs")), None)
        self.assertFalse(check(low, "keyword_density").passed)
        stuffed = article_body(extra=" ".join(["Running shoes are great running shoes."] * 40))
        r = seo.seo_score(mk_draft(stuffed))
        self.assertGreater(r.density, 3.0)
        self.assertGreater(r.penalty, 0)
        self.assertFalse(check(r, "keyword_density").passed)
        self.assertIn("KEYWORD_STUFFING", [i.code for i in r.issues])
        clean = seo.seo_score(mk_draft(article_body()))
        self.assertGreater(clean.score, r.score)

    def test_between_25_and_3_percent_fails_without_the_stuffing_penalty(self):
        words = prose(300).split()
        text = " ".join(words)
        # 8 hits in about 310 words is about 2.6 percent
        body = "# Running shoes\n\n" + text + " " + " ".join(["Running shoes."] * 8)
        r = seo.seo_score(mk_draft(body))
        self.assertTrue(2.5 < r.density <= 3.0, r.density)
        self.assertFalse(check(r, "keyword_density").passed)
        self.assertEqual(r.penalty, 0.0)

    def test_sentence_length_check(self):
        long_sentence = " ".join(["word"] * 45) + "."
        self.assertTrue(check(seo.seo_score(mk_draft(article_body())), "sentence_length").passed)
        heavy = "# Running shoes\n\n" + " ".join([long_sentence] * 6)
        report = seo.seo_score(mk_draft(heavy))
        self.assertFalse(check(report, "sentence_length").passed)
        self.assertIn("LONG_SENTENCES", [i.code for i in report.issues])

    def test_internal_links_check_and_not_applicable_case(self):
        links = [{"url": f"/p{i}", "anchor": f"Page {i}"} for i in range(3)]
        body = article_body(extra="See [one](/p0), [two](/p1) and [three](/p2).")
        ok = check(seo.seo_score(mk_draft(body, internal_links=links)), "internal_links")
        self.assertTrue(ok.passed and ok.weight > 0)
        few = check(seo.seo_score(mk_draft(article_body(extra="See [one](/p0)."), internal_links=links)), "internal_links")
        self.assertFalse(few.passed)
        na = check(seo.seo_score(mk_draft(article_body())), "internal_links")
        self.assertTrue(na.passed)
        self.assertEqual(na.weight, 0.0)

    def test_faq_and_sources_checks(self):
        self.assertTrue(check(seo.seo_score(mk_draft(article_body(faq=3))), "faq").passed)
        self.assertFalse(check(seo.seo_score(mk_draft(article_body(faq=2))), "faq").passed)
        self.assertTrue(check(seo.seo_score(mk_draft("# T\n\nQ: What is it?\nA: A thing that helps runners pick shoes.\n\nQ: Why?\nA: Because fit matters a lot for knees.\n\nQ: How?\nA: With a short gait check at a store.")), "faq").passed)
        self.assertFalse(check(seo.seo_score(mk_draft(article_body(cites=1))), "sources").passed)
        self.assertTrue(check(seo.seo_score(mk_draft(article_body(cites=2))), "sources").passed)
        cited = "# T\n\nOne claim [[cite:a]]. Another claim [[cite:b]]."
        self.assertTrue(check(seo.seo_score(mk_draft(cited)), "sources").passed)

    def test_word_count_within_25_percent_of_the_target(self):
        body = article_body()
        words = seo.count_words(seo.plain_text(seo.front_matter(body)[1]))
        near = check(seo.seo_score(mk_draft(body, word_target=words)), "word_count")
        self.assertTrue(near.passed)
        self.assertFalse(check(seo.seo_score(mk_draft(body, word_target=words * 3)), "word_count").passed)
        self.assertFalse(check(seo.seo_score(mk_draft(body, word_target=1500)), "word_count").passed)

    def test_no_keyword_skips_keyword_checks(self):
        d = Draft(format="x", lang="en", hook="", body=article_body(), parts={}, meta={})
        r = seo.seo_score(d)
        self.assertEqual(check(r, "keyword_density").weight, 0.0)
        self.assertIsNone(r.density)
        self.assertTrue(check(r, "title").passed)

    def test_score_is_bounded_and_drops_with_defects(self):
        for body in ("", "# T", article_body(), article_body(h1=3, faq=0, cites=0)):
            r = seo.seo_score(mk_draft(body))
            self.assertTrue(0 <= r.score <= 100)
        self.assertGreater(seo.seo_score(mk_draft(article_body())).score, seo.seo_score(mk_draft(article_body(h1=3, faq=0, cites=0))).score)


class QualityGateTests(unittest.TestCase):
    def codes(self, issues, severity=None):
        return [i.code for i in issues if severity is None or i.severity == severity]

    def test_offline_draft_is_blocked_by_open_slots_but_experience_comes_from_facts(self):
        sk = seo.build_seo_article(EN)
        d = sk.render(OfflineWriter().fill(sk, EN))
        issues = seo.quality_gate(d, EN)
        self.assertEqual(self.codes(issues, "error"), ["SLOTS_OPEN"])
        self.assertIn("answer_lead", issues[0].message)
        self.assertIn("HUMAN_REVIEW_REQUIRED", self.codes(issues, "info"))

    def test_no_first_party_experience_is_an_error_even_when_everything_else_is_filled(self):
        sk = seo.build_seo_article(BARE_EN, options={"word_target": 650, "sections": 3})
        fills = {s.id: prose(40, i) for i, s in enumerate(sk.slots) if s.id not in ("title", "meta_description", "h1", "experience")}
        d = sk.render(fills)
        self.assertEqual(d.slots_open, ["experience"])
        d2 = sk.render({**fills, "experience": "We tried it."})
        issues = seo.quality_gate(d2, BARE_EN)
        self.assertIn("NOT_PUBLISHABLE_NO_EXPERIENCE", self.codes(issues, "error"))
        d3 = sk.render({**fills, "experience": "Across 40 customer calls last spring we saw the same onboarding mistake every week."})
        self.assertNotIn("NOT_PUBLISHABLE_NO_EXPERIENCE", self.codes(seo.quality_gate(d3, BARE_EN)))

    def test_fully_written_article_has_no_errors_but_still_needs_a_human(self):
        _, d = filled_article()
        issues = seo.quality_gate(d, EN)
        self.assertEqual(self.codes(issues, "error"), [])
        self.assertEqual(self.codes(issues, "warn"), [])
        self.assertEqual(self.codes(issues), ["HUMAN_REVIEW_REQUIRED"])
        self.assertEqual(issues[-1].severity, "info")

    def test_thin_sources_warning(self):
        thin = Brief(brand="B", topic="t", audience="a", keyword="running shoes", sources=[SOURCES[0]])
        d = Draft(format="x", lang="en", hook="", body="# T\n\nBody.", parts={}, meta={})
        self.assertIn("THIN_SOURCES", self.codes(seo.quality_gate(d, thin), "warn"))
        two = Brief(brand="B", topic="t", audience="a", sources=SOURCES[:2])
        self.assertNotIn("THIN_SOURCES", self.codes(seo.quality_gate(d, two)))
        facts_and_source = Brief(brand="B", topic="t", audience="a", sources=[SOURCES[0]], facts=["Our lab measured 412 runners last year."])
        self.assertNotIn("THIN_SOURCES", self.codes(seo.quality_gate(d, facts_and_source)))
        cited = Draft(format="x", lang="en", hook="", body="# T\n\nA [[cite:s1]]. B [[cite:s2]].", parts={}, meta={})
        self.assertNotIn("THIN_SOURCES", self.codes(seo.quality_gate(cited, thin)))

    def test_generic_intro_in_english_and_czech(self):
        for text in ("In today's fast-paced world, shoes matter a lot.", "In today’s fast-paced world, shoes matter.", "Have you ever wondered which shoes fit?"):
            d = Draft(format="x", lang="en", hook="", body="# T\n\n" + text, parts={}, meta={})
            self.assertIn("GENERIC_INTRO", self.codes(seo.quality_gate(d, EN), "warn"), text)
        for text in ("V dnešní rychlé době je výběr bot důležitý.", "v dnesni rychle dobe je vyber bot dulezity", "V tomto článku se dozvíte vše o botách."):
            d = Draft(format="x", lang="cs", hook="", body="# T\n\n" + text, parts={}, meta={})
            issue = next(i for i in seo.quality_gate(d, CS) if i.code == "GENERIC_INTRO")
            self.assertIn("klišé", issue.message)

    def test_generic_phrase_after_the_intro_is_not_flagged(self):
        body = "# T\n\n" + prose(150) + "\n\nIn today's fast-paced world this is late."
        d = Draft(format="x", lang="en", hook="", body=body, parts={}, meta={})
        self.assertNotIn("GENERIC_INTRO", self.codes(seo.quality_gate(d, EN)))

    def test_gate_without_a_brief_uses_the_draft_parts(self):
        _, d = filled_article()
        self.assertEqual(self.codes(seo.quality_gate(d), "error"), [])
        sk = seo.build_seo_article(BARE_EN)
        issues = seo.quality_gate(sk.render(), None)
        self.assertIn("NOT_PUBLISHABLE_NO_EXPERIENCE", self.codes(issues, "error"))

    def test_czech_messages(self):
        sk = seo.build_seo_article(CS_PLAIN)
        issues = seo.quality_gate(sk.render(), CS_PLAIN)
        msg = {i.code: i.message for i in issues}
        self.assertIn("Nelze zveřejnit", msg["NOT_PUBLISHABLE_NO_EXPERIENCE"])
        self.assertIn("zástupné", msg["SLOTS_OPEN"])
        self.assertIn("člověk", msg["HUMAN_REVIEW_REQUIRED"])

    def test_registry_and_validator(self):
        self.assertEqual([f.id for f in seo.FORMAT_SPECS], ["seo_article"])
        spec = seo.FORMAT_SPECS[0]
        self.assertEqual((spec.family, spec.platform), ("article", "blog"))
        self.assertIs(spec.build, seo.build_seo_article)
        d = spec.build(EN).render()
        codes = self.codes(spec.validate(d))
        self.assertIn("SLOTS_OPEN", codes)
        self.assertIn("HUMAN_REVIEW_REQUIRED", codes)
        self.assertNotIn(chr(0x2014), json.dumps([spec.name_en, spec.name_cs, spec.description_en, spec.description_cs]))


if __name__ == "__main__":
    unittest.main()
