"""The committed MITO LIGHT example: still free of errors, and its files still match what the generator writes."""
import tempfile
import unittest
from pathlib import Path

from dopamine_king.generate.packs import build_pack
from dopamine_king.generate.providers import FileWriter
from dopamine_king.verticals import load_vertical

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "mito-light-cs"
FORMATS = ["instagram_caption", "short_video_script", "seo_article", "geo_answer_page", "newsletter"]
V = load_vertical("pbm")


def build():
    return build_pack(V.briefs(V.ledger())["mito-light-cs"], FORMATS, writer=FileWriter(EXAMPLE / "fills.json"), ledger=V.ledger())


class MitoLightExampleTests(unittest.TestCase):
    def test_the_example_has_no_errors_and_only_the_slots_that_need_real_data_are_open(self):
        pack = build()
        self.assertEqual(pack.summary["errors"], 0, [i for it in pack.items for i in it.issues if i["severity"] == "error"])
        self.assertEqual({it.verdict for it in pack.items} - {"ok", "review"}, set())
        open_slots = {slot for it in pack.items for slot in it.slots_open}
        self.assertEqual(open_slots, {"author_box", "updated", "quote_1_text", "quote_1_name", "quote_1_credential", "footer_identity"})

    def test_no_slot_of_the_example_breaks_its_limits(self):
        writer = FileWriter(EXAMPLE / "fills.json")
        build_pack(V.briefs(V.ledger())["mito-light-cs"], FORMATS, writer=writer, ledger=V.ledger())
        self.assertEqual(writer.violations, {})

    def test_the_committed_files_match_what_the_generator_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            written = [p for p in build().save(tmp) if p.name != "pack.json"]
            self.assertTrue(written)
            for path in written:
                committed = EXAMPLE / "out" / path.name
                self.assertTrue(committed.exists(), f"{committed} is missing: regenerate the example (see examples/mito-light-cs/README.md)")
                self.assertEqual(committed.read_text("utf-8"), path.read_text("utf-8"),
                                 f"{committed.name} is out of date: regenerate the example (see examples/mito-light-cs/README.md)")
            names = {p.name for p in written}
            extra = {p.name for p in (EXAMPLE / "out").iterdir()} - names
            self.assertEqual(extra, set(), "files in out/ that the generator no longer writes")

    def test_the_example_has_no_long_dashes(self):
        for path in [EXAMPLE / "fills.json", EXAMPLE / "README.md", *(EXAMPLE / "out").iterdir()]:
            text = path.read_text("utf-8")
            self.assertNotIn(chr(0x2014), text, path.name)
            self.assertNotIn(chr(0x2013), text, path.name)


if __name__ == "__main__":
    unittest.main()
