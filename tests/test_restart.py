"""Verify persistence after the writer process exits, not just another connection."""
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from wordloom.library import Library


class RestartTests(unittest.TestCase):
    def test_committed_vocabulary_and_review_survive_process_exit(self):
        with TemporaryDirectory(prefix="wordloom-重启-") as directory:
            path = Path(directory) / "词库.sqlite3"
            code = '''
import json, sys
from pathlib import Path
from wordloom.library import Library
lib = Library(Path(sys.argv[1]), clock=lambda: 1800000000)
e = lib.add("serendipity", "中文上下文", "机缘巧合", "test-model")
e = lib.review(e.id, "good", expected_revision=e.revision)
print(json.dumps({"id": e.id, "due": e.due}))
# Deliberately exit without Library.close(): committed WAL must survive.
'''
            result = subprocess.run([sys.executable, "-c", code, str(path)],
                                    env=dict(os.environ, PYTHONUTF8="1"), capture_output=True,
                                    text=True, encoding="utf-8", timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            saved = json.loads(result.stdout)
            lib = Library(path, clock=lambda: 1800000000)
            try:
                e = lib.get(saved["id"])
                self.assertEqual((e.context, e.meaning), ("中文上下文", "机缘巧合"))
                self.assertEqual((e.repetitions, e.interval, e.revision), (1, 1, 1))
                self.assertEqual(e.due, saved["due"])
                self.assertEqual(lib.due_entries(), [])
                self.assertEqual(lib.conn.execute("SELECT count(*) FROM reviews").fetchone()[0], 1)
            finally:
                lib.close()
