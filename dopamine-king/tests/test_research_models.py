import unittest

from dopamine_king.research.grading import DESIGN_SCORES
from dopamine_king.research.models import (
    DESIGNS, DIRECTIONS, DOI_RE, EvidenceLink, Study, clean_text, fold, format_author, format_author_parts,
    make_study_id, normalize_doi, normalize_title,
)


class DoiTests(unittest.TestCase):
    def test_normalize_doi_strips_prefixes_and_lowercases(self):
        for raw in ("10.1509/JMR.10.0353", "https://doi.org/10.1509/jmr.10.0353", "http://dx.doi.org/10.1509/jmr.10.0353",
                    "doi:10.1509/jmr.10.0353", "  DOI: 10.1509/JMR.10.0353  "):
            self.assertEqual(normalize_doi(raw), "10.1509/jmr.10.0353", raw)

    def test_normalize_doi_rejects_garbage(self):
        for raw in (None, "", "   ", "doi.org", "10.12/short-registrant", "11.1234/x", "10.1234/", 42):
            self.assertIsNone(normalize_doi(raw), raw)

    def test_doi_regex_matches_the_brief(self):
        self.assertTrue(DOI_RE.match("10.1016/s0165-0173(98)00019-8"))
        self.assertFalse(DOI_RE.match("10.1016"))


class TextHelperTests(unittest.TestCase):
    def test_clean_text_strips_markup_entities_and_whitespace(self):
        self.assertEqual(clean_text("  <b>Bold</b>  &amp;\n\tplain <jats:p>para</jats:p><jats:p>two</jats:p> "),
                         "Bold & plain para two")
        self.assertEqual(clean_text(None), "")

    def test_fold_is_case_and_diacritics_insensitive(self):
        self.assertEqual(fold("Žluťoučký KŮŇ"), "zlutoucky kun")
        self.assertEqual(fold(None), "")

    def test_normalize_title_reduces_to_words(self):
        self.assertEqual(normalize_title("What Makes <i>Online</i> Content Viral?"), "what makes online content viral")
        self.assertEqual(normalize_title("Does gamification work? -- A review"), normalize_title("Does Gamification Work: A Review"))


class AuthorFormatTests(unittest.TestCase):
    def test_given_family_order(self):
        self.assertEqual(format_author("Jonah Berger"), "Berger, J.")
        self.assertEqual(format_author("Katherine L. Milkman"), "Milkman, K. L.")
        self.assertEqual(format_author("K.L. Milkman"), "Milkman, K. L.")
        self.assertEqual(format_author("Jean-Pierre Dupont"), "Dupont, J.-P.")

    def test_family_given_order_and_particles(self):
        self.assertEqual(format_author("Berger, Jonah"), "Berger, J.")
        self.assertEqual(format_author("Jay J. Van Bavel"), "Van Bavel, J. J.")
        self.assertEqual(format_author("Anna van der Meer"), "van der Meer, A.")

    def test_single_names_and_empty(self):
        self.assertEqual(format_author("Aristotle"), "Aristotle")
        self.assertIsNone(format_author(None))
        self.assertIsNone(format_author("   "))

    def test_parts(self):
        self.assertEqual(format_author_parts("Jane Q.", "Doe"), "Doe, J. Q.")
        self.assertEqual(format_author_parts(None, "Consortium"), "Consortium")
        self.assertIsNone(format_author_parts(None, None))


class StudyIdTests(unittest.TestCase):
    def test_priority_doi_then_arxiv_then_openalex_then_slug(self):
        self.assertEqual(make_study_id(doi="10.1/ABC", arxiv_id="1", openalex_id="W1", slug="s"), "doi:10.1/abc")
        self.assertEqual(make_study_id(arxiv_id="2311.09735", openalex_id="W1", slug="s"), "arxiv:2311.09735")
        self.assertEqual(make_study_id(openalex_id="W1", slug="s"), "oa:W1")
        self.assertEqual(make_study_id(slug="eyal-2014"), "seed:eyal-2014")
        with self.assertRaises(ValueError):
            make_study_id()


class DataclassTests(unittest.TestCase):
    def test_study_defaults_follow_the_brief(self):
        s = Study(id="seed:x", title="X")
        self.assertEqual((s.design, s.source, s.confidence, s.grade, s.grade_score), ("unknown", "seed", "medium", "", 0.0))
        self.assertEqual((s.verified, s.retracted, s.peer_reviewed, s.verification_note), (False, False, None, ""))
        self.assertEqual(s.authors, [])

    def test_round_trip_and_tolerance_for_unknown_keys(self):
        s = Study(id="doi:10.1/x", title="T", authors=["Doe, J."], year=2020, doi="10.1/x", design="rct", grade="A", grade_score=0.9)
        data = s.to_dict()
        self.assertEqual(Study.from_dict(data), s)
        self.assertEqual(Study.from_dict({**data, "future_field": 1}), s)

    def test_evidence_link_defaults(self):
        link = EvidenceLink.from_dict({"tactic_id": "t", "study_id": "s", "direction": "supports", "note_en": "a", "note_cs": "b"})
        self.assertEqual((link.caveat_en, link.caveat_cs), ("", ""))

    def test_design_vocabulary_matches_the_grading_table(self):
        self.assertEqual(set(DESIGNS), set(DESIGN_SCORES))
        self.assertEqual(DIRECTIONS, ("supports", "mixed", "contradicts", "context"))


if __name__ == "__main__":
    unittest.main()
