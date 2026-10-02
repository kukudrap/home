"""Bring your own writer: the slot template, FileWriter and the forge command with --writer file."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from dopamine_king import cli
from dopamine_king.generate.packs import build_pack, slot_template
from dopamine_king.generate.providers import FileWriter, WriterError, select_writer
from dopamine_king.verticals import load_vertical

V = load_vertical("pbm")
BRIEF = V.briefs(V.ledger())["mito-light-cs"]
DASHES = (chr(0x2014), chr(0x2013))


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class FileCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "fills.json"

    def write(self, data) -> Path:
        self.path.write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False), "utf-8")
        return self.path

    def pack(self, data, formats=("instagram_caption",)):
        writer = FileWriter(self.write(data))
        return writer, build_pack(BRIEF, list(formats), writer=writer, ledger=V.ledger())


class SlotTemplateTests(unittest.TestCase):
    def test_the_template_lists_every_slot_with_its_limits_and_an_empty_text(self):
        template = slot_template(BRIEF, ["instagram_caption", "short_video_script"], ledger=V.ledger())
        self.assertIn("_help", template)
        self.assertEqual([k for k in template if not k.startswith("_")], ["instagram_caption", "short_video_script"])
        slots = template["instagram_caption"]
        self.assertEqual(set(slots), {"hook", "body", "cta", "hashtags"})
        for slot in slots.values():
            self.assertEqual(slot["text"], "")
            self.assertTrue(slot["instruction"])
            self.assertIsInstance(slot["limits"], dict)
        self.assertEqual(slots["hook"]["limits"]["max_chars"], 125)
        self.assertTrue(slots["cta"]["default"])

    def test_unknown_formats_are_skipped(self):
        template = slot_template(BRIEF, ["instagram_caption", "no_such_format"], ledger=V.ledger())
        self.assertEqual([k for k in template if not k.startswith("_")], ["instagram_caption"])

    def test_the_template_is_valid_input_for_the_writer(self):
        template = slot_template(BRIEF, ["instagram_caption"], ledger=V.ledger())
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t.json"
            path.write_text(json.dumps(template, ensure_ascii=False), "utf-8")
            writer = FileWriter(path)
            self.assertEqual({k: v for k, v in writer.by_format.items() if v}, {})          # nothing filled yet: the defaults apply
            self.assertEqual(writer.flat, {})


class FileWriterTests(FileCase):
    BODY = "Večerní sezení pod červeným světlem je pro mnoho lidí příjemná rutina po tréninku.\n\nPřečtěte si návod a chraňte oči."

    def test_slots_are_filled_by_format_flat_and_as_text_objects(self):
        writer, pack = self.pack({"instagram_caption": {"body": self.BODY, "cta": {"text": "Podívejte se na panely"}}, "hashtags": "#MITOLIGHT #regenerace"})
        item = pack.items[0]
        self.assertIn("Večerní sezení", item.body)
        self.assertIn("Podívejte se na panely", item.body)
        self.assertIn("#MITOLIGHT #regenerace", item.body)
        self.assertEqual(writer.used, {("instagram_caption", "body"), ("instagram_caption", "cta"), ("instagram_caption", "hashtags")})
        self.assertEqual(item.slots_open, [])
        self.assertEqual(pack.writer, "file")

    def test_a_pack_written_from_the_template_shape_works(self):
        template = slot_template(BRIEF, ["instagram_caption"], ledger=V.ledger())
        template["instagram_caption"]["body"]["text"] = self.BODY
        writer, pack = self.pack(template)
        self.assertIn("Večerní sezení", pack.items[0].body)
        self.assertEqual(writer.used, {("instagram_caption", "body")})

    def test_empty_slots_keep_their_defaults_and_open_slots_stay_visible(self):
        _, pack = self.pack({"instagram_caption": {"body": "", "cta": "   "}})
        item = pack.items[0]
        self.assertIn("[[ADD:", item.body)
        self.assertTrue(item.slots_open)

    def test_long_dashes_are_normalised(self):
        _, pack = self.pack({"instagram_caption": {"body": f"Rutina {DASHES[0]} bez slibů {DASHES[1]} s návodem."}})
        self.assertFalse(any(d in pack.items[0].body for d in DASHES))

    def test_notes_and_unknown_slots_are_ignored(self):
        writer, pack = self.pack({"_note": "my notes", "instagram_caption": {"_why": "x", "nonsense": "text", "body": self.BODY}, "other_format": {"body": "no"}})
        self.assertEqual(writer.used, {("instagram_caption", "body")})
        self.assertNotIn("my notes", pack.items[0].body)

    def test_limits_are_reported_but_not_enforced(self):
        writer, pack = self.pack({"instagram_caption": {"hook": "x" * 300}})
        self.assertIn("instagram_caption.hook", writer.violations)
        self.assertIn("300 characters", writer.violations["instagram_caption.hook"][0])
        self.assertEqual(len(pack.items), 1)

    def test_the_trust_shield_still_judges_what_was_written(self):
        _, pack = self.pack({"instagram_caption": {"body": "Červené světlo léčí bolest zad a vyléčí vás za 14 dní."}})
        codes = {i["code"] for i in pack.items[0].issues}
        self.assertIn("CLAIM_MEDICAL", codes)
        self.assertEqual(pack.items[0].verdict, "blocked")

    def test_a_compliant_text_passes_without_errors(self):
        _, pack = self.pack({"instagram_caption": {"body": self.BODY}})
        self.assertEqual([i for i in pack.items[0].issues if i["severity"] == "error"], [])

    def test_a_bad_file_is_a_clear_error(self):
        for data in ("{not json", "[1, 2]", '"text"'):
            with self.assertRaises(WriterError):
                FileWriter(self.write(data))
        with self.assertRaises(WriterError):
            FileWriter(Path(self.dir.name) / "missing.json")

    def test_select_writer_knows_the_file_writer(self):
        self.assertEqual(select_writer("file", path=self.write({})).name, "file")


class CommandTests(FileCase):
    def forge(self, *extra):
        return run_cli("forge", "--vertical", "pbm", "--sample", "mito-light-cs", "--formats", "instagram_caption", *extra)

    def test_emit_fill_and_forge_round_trip(self):
        code, out, _ = self.forge("--emit-slots", str(self.path))
        self.assertEqual(code, 0)
        self.assertIn("Wrote the slots of 1 formats", out)
        template = json.loads(self.path.read_text("utf-8"))
        template["instagram_caption"]["body"]["text"] = "Večerní sezení je příjemná rutina po tréninku. Přečtěte si návod a chraňte oči."
        self.path.write_text(json.dumps(template, ensure_ascii=False), "utf-8")
        outdir = Path(self.dir.name) / "out"
        code, _, err = self.forge("--writer", "file", "--fills", str(self.path), "--out", str(outdir), "--quiet")
        self.assertEqual(code, 0)
        self.assertIn("[file] 1 slots filled", err)
        self.assertTrue((outdir / "pack.json").exists())
        pack = json.loads((outdir / "pack.json").read_text("utf-8"))
        self.assertEqual(pack["writer"], "file")
        self.assertIn("Večerní sezení", pack["items"][0]["body"])

    def test_the_file_writer_needs_a_fills_file(self):
        with self.assertRaises(SystemExit) as ctx:
            self.forge("--writer", "file")
        self.assertIn("--fills", str(ctx.exception))

    def test_a_broken_fills_file_stops_with_a_message(self):
        with self.assertRaises(SystemExit) as ctx:
            self.forge("--writer", "file", "--fills", str(self.write("{nope")))
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_limit_problems_are_printed(self):
        self.write({"instagram_caption": {"hook": "x" * 300}})
        _, _, err = self.forge("--writer", "file", "--fills", str(self.path), "--quiet")
        self.assertIn("instagram_caption.hook breaks its limits", err)


if __name__ == "__main__":
    unittest.main()
