import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from wordloom.library import Library, LibraryError


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.now = 1800000000
        self.lib = Library(self.path / "library.db", clock=lambda: self.now)

    def tearDown(self):
        self.lib.close()
        self.temp.cleanup()

    def add(self, text="serendipity", context="a fortunate encounter", meaning="意外的好运"):
        return self.lib.add(text, context, meaning, "custom-model")

    def test_crud_search_unicode_and_reopen(self):
        e = self.add()
        self.assertEqual(self.lib.search("好运")[0].id, e.id)
        self.assertEqual(self.lib.search("FORTUNATE")[0].id, e.id)
        edited = self.lib.update(e.id, "serendipity", e.context, "机缘巧合", expected_revision=e.revision)
        self.lib.close()
        self.lib = Library(self.path / "library.db", clock=lambda: self.now)
        self.assertEqual(self.lib.get(e.id).meaning, "机缘巧合")
        self.assertEqual(edited.revision, 1)
        self.lib.delete(e.id)
        self.assertEqual(self.lib.search(), [])

    def test_search_literal_metacharacters_and_sql(self):
        self.add("100%", "under_score", "含百分号")
        self.add("another", "normal", "普通词")
        self.assertEqual(len(self.lib.search("%")), 1)
        self.assertEqual(len(self.lib.search("_")), 1)
        self.assertEqual(self.lib.search("' OR 1=1 --"), [])

    def test_duplicate_and_stale_edit(self):
        e = self.add()
        with self.assertRaises(LibraryError):
            self.add("SERENDIPITY")
        self.lib.update(e.id, e.text, e.context, "更新", expected_revision=0)
        with self.assertRaises(LibraryError):
            self.lib.update(e.id, e.text, e.context, "过期更新", expected_revision=0)

    def test_review_progress_reopen_no_double_grade(self):
        e = self.add()
        self.assertEqual(len(self.lib.due_entries()), 1)
        first = self.lib.review(e.id, "good", expected_revision=0)
        self.assertEqual(first.due, self.now + 86400)
        self.assertEqual(first.repetitions, 1)
        with self.assertRaises(LibraryError):
            self.lib.review(e.id, "good", expected_revision=0)
        self.lib.close()
        self.lib = Library(self.path / "library.db", clock=lambda: self.now)
        self.assertEqual(self.lib.due_entries(), [])
        self.now += 86400
        second = self.lib.review(e.id, "again", expected_revision=1)
        self.assertEqual(second.lapses, 1)
        self.assertEqual(second.due, self.now + 600)
        self.assertEqual(self.lib.conn.execute("SELECT count(*) FROM reviews").fetchone()[0], 2)
        self.lib.delete(e.id)
        self.assertEqual(self.lib.conn.execute("SELECT count(*) FROM reviews").fetchone()[0], 0)

    def test_hard_and_good_schedule_and_invalid_grade(self):
        e = self.add()
        with self.assertRaises(LibraryError):
            self.lib.review(e.id, "anything", expected_revision=0)
        e = self.lib.review(e.id, "hard", expected_revision=0)
        self.now += 86400
        e = self.lib.review(e.id, "good", expected_revision=e.revision)
        self.assertEqual(e.interval, 2)

    def test_json_roundtrip_preserves_progress_csv_resets(self):
        e = self.add(context='包含,"引号"\n第二行')
        self.lib.review(e.id, "good", expected_revision=0)
        for extension in ("json", "csv"):
            path = self.path / ("out." + extension)
            self.lib.export_file(path)
            other = Library(self.path / (extension + ".db"), clock=lambda: self.now)
            try:
                self.assertEqual(other.import_file(path), (1, 0))
                self.assertEqual(other.import_file(path), (0, 1))
                imported = other.search()[0]
                self.assertEqual(imported.context, e.context)
                self.assertEqual(imported.repetitions, 1 if extension == "json" else 0)
                self.assertEqual(imported.meaning, e.meaning)
                self.assertNotIn("api_key", path.read_text(encoding="utf-8"))
            finally:
                other.close()

    def test_invalid_import_all_or_nothing(self):
        path = self.path / "bad.json"
        rows = [{"text": "valid", "context": "", "meaning": "有效", "model": ""}, {"text": "invalid", "meaning": "", "api_key": "never-import"}]
        path.write_text(json.dumps({"format": "wordloom-library", "version": 1, "entries": rows}))
        with self.assertRaises(LibraryError):
            self.lib.import_file(path)
        self.assertEqual(self.lib.search(), [])

    def test_invalid_review_import_is_rejected(self):
        e = self.add()
        path = self.path / "data.json"
        self.lib.export_file(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["entries"][0]["review"]["due"] = -1
        path.write_text(json.dumps(data))
        with self.assertRaises(LibraryError):
            self.lib.import_file(path)
        self.assertEqual(self.lib.get(e.id).revision, 0)

    def test_invalid_entry_no_partial_write(self):
        for text, meaning in [("", "释义"), ("word", ""), ("x" * 20001, "释义")]:
            with self.assertRaises(LibraryError):
                self.add(text=text, meaning=meaning)
        self.assertEqual(self.lib.search(), [])

    def test_large_meaning_csv_roundtrip(self):
        self.add(meaning="定义" * 80000)
        path = self.path / "large.csv"
        self.lib.export_file(path)
        second = Library(self.path / "second.db")
        try:
            self.assertEqual(second.import_file(path), (1, 0))
            self.assertEqual(len(second.search()[0].meaning), 160000)
        finally:
            second.close()
