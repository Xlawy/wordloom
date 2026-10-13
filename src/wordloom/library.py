from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from .config import atomic_write


class LibraryError(ValueError):
    pass


@dataclass(frozen=True)
class Entry:
    id: str
    text: str
    context: str
    meaning: str
    model: str
    created: int
    updated: int
    due: int
    interval: int
    repetitions: int
    lapses: int
    revision: int


def validate_text(text: str, context: str, meaning: str, model: str = "") -> None:
    for name, value, maximum in (("词语/原文", text, 20000), ("上下文", context, 40000), ("释义", meaning, 200000), ("模型", model, 256)):
        if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
            raise LibraryError(f"{name}格式不正确或超过长度限制。")
    if not text.strip() or not meaning.strip():
        raise LibraryError("原文和释义不能为空。")


def fingerprint(text: str, context: str) -> str:
    return hashlib.sha256(json.dumps([text.strip().casefold(), context.strip()], ensure_ascii=False).encode()).hexdigest()


class Library:
    def __init__(self, path: Path, clock=time.time):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA journal_mode=WAL")
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            self.conn.close()
            raise LibraryError("词库由更新版本创建，当前版本不能打开。")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS entries (
              id TEXT PRIMARY KEY, text TEXT NOT NULL, context TEXT NOT NULL,
              meaning TEXT NOT NULL, model TEXT NOT NULL, fingerprint TEXT UNIQUE NOT NULL,
              created INTEGER NOT NULL, updated INTEGER NOT NULL, due INTEGER NOT NULL,
              interval INTEGER NOT NULL DEFAULT 0, repetitions INTEGER NOT NULL DEFAULT 0,
              lapses INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS entries_due ON entries(due);
            CREATE TABLE IF NOT EXISTS reviews (
              id INTEGER PRIMARY KEY, entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
              reviewed INTEGER NOT NULL, grade TEXT NOT NULL, old_due INTEGER NOT NULL,
              new_due INTEGER NOT NULL);
            PRAGMA user_version=1;
        """)

    def close(self):
        self.conn.close()

    @staticmethod
    def _entry(row) -> Entry | None:
        return Entry(**{k: row[k] for k in Entry.__dataclass_fields__}) if row else None

    def get(self, ident: str) -> Entry | None:
        return self._entry(self.conn.execute("SELECT * FROM entries WHERE id=?", (ident,)).fetchone())

    def search(self, text: str = "") -> list[Entry]:
        # Parameterized substring search. Escape LIKE metacharacters, preserve Chinese.
        pattern = "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        rows = self.conn.execute(r"""SELECT * FROM entries WHERE text LIKE ? ESCAPE '\'
            OR context LIKE ? ESCAPE '\' OR meaning LIKE ? ESCAPE '\' ORDER BY updated DESC, id""", (pattern,) * 3)
        return [self._entry(row) for row in rows]

    def add(self, text: str, context: str, meaning: str, model: str = "") -> Entry:
        validate_text(text, context, meaning, model)
        ident = uuid4().hex
        now = int(self.clock())
        try:
            with self.conn:
                self.conn.execute("""INSERT INTO entries
                    (id,text,context,meaning,model,fingerprint,created,updated,due)
                    VALUES (?,?,?,?,?,?,?,?,?)""", (ident, text.strip(), context.strip(), meaning.strip(), model,
                    fingerprint(text, context), now, now, now))
        except sqlite3.IntegrityError:
            raise LibraryError("相同原文和上下文已在词库中，请在词库中编辑。") from None
        return self.get(ident)

    def update(self, ident: str, text: str, context: str, meaning: str, *, expected_revision: int) -> Entry:
        validate_text(text, context, meaning)
        try:
            with self.conn:
                cur = self.conn.execute("""UPDATE entries SET text=?,context=?,meaning=?,fingerprint=?,updated=?,revision=revision+1
                    WHERE id=? AND revision=?""", (text.strip(), context.strip(), meaning.strip(), fingerprint(text, context),
                    int(self.clock()), ident, expected_revision))
                if cur.rowcount != 1:
                    raise LibraryError("条目已改变或删除，请刷新后再编辑。")
        except sqlite3.IntegrityError:
            raise LibraryError("修改后与现有条目重复。") from None
        return self.get(ident)

    def delete(self, ident: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM entries WHERE id=?", (ident,))

    def due_entries(self) -> list[Entry]:
        return [self._entry(r) for r in self.conn.execute("SELECT * FROM entries WHERE due<=? ORDER BY due, created, id", (int(self.clock()),))]

    def review(self, ident: str, grade: str, *, expected_revision: int) -> Entry:
        if grade not in ("again", "hard", "good"):
            raise LibraryError("未知评分。")
        now = int(self.clock())
        with self.conn:
            # Write lock and revision check make stale/double ratings fail atomically.
            self.conn.execute("BEGIN IMMEDIATE")
            old = self.get(ident)
            if old is None or old.revision != expected_revision or old.due > now:
                raise LibraryError("这张卡已评分、变更或尚未到期，请刷新复习列表。")
            if grade == "again":
                interval, due = 0, now + 600
            elif grade == "hard":
                interval = min(3650, max(1, round(old.interval * 1.2)))
                due = now + interval * 86400
            else:
                interval = min(3650, 1 if old.interval == 0 else max(old.interval + 1, round(old.interval * 2.2)))
                due = now + interval * 86400
            self.conn.execute("""UPDATE entries SET due=?,interval=?,repetitions=repetitions+1,
                lapses=lapses+?,revision=revision+1,updated=? WHERE id=?""",
                (due, interval, int(grade == "again"), now, ident))
            self.conn.execute("INSERT INTO reviews(entry_id,reviewed,grade,old_due,new_due) VALUES(?,?,?,?,?)",
                              (ident, now, grade, old.due, due))
        return self.get(ident)

    def export_file(self, path: Path) -> int:
        entries = self.search()
        columns = ("text", "context", "meaning", "model")
        if path.suffix.lower() == ".csv":
            stream = io.StringIO(newline="")
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            for e in entries:
                writer.writerow({k: getattr(e, k) for k in columns})
            output = stream.getvalue()
        elif path.suffix.lower() == ".json":
            output = json.dumps({"format": "wordloom-library", "version": 1, "entries": [
                {**{k: getattr(e, k) for k in columns}, "review": {k: getattr(e, k) for k in ("due", "interval", "repetitions", "lapses")}}
                for e in entries]}, ensure_ascii=False, indent=2)
        else:
            raise LibraryError("请选择 .json 或 .csv 文件。")
        atomic_write(path, output)
        return len(entries)

    def import_file(self, path: Path) -> tuple[int, int]:
        if path.stat().st_size > 20_000_000:
            raise LibraryError("导入文件不能超过 20 MB。")
        try:
            text = path.read_text(encoding="utf-8-sig")
            if path.suffix.lower() == ".csv":
                reader = csv.DictReader(io.StringIO(text, newline=""))
                if not reader.fieldnames or set(reader.fieldnames) != {"text", "context", "meaning", "model"}:
                    raise ValueError()
                old_limit = csv.field_size_limit(250000)
                try:
                    rows = list(reader)
                finally:
                    csv.field_size_limit(old_limit)
            elif path.suffix.lower() == ".json":
                data = json.loads(text)
                if data.get("format") != "wordloom-library" or data.get("version") != 1:
                    raise ValueError()
                rows = data["entries"]
            else:
                raise ValueError()
            if not isinstance(rows, list) or len(rows) > 10000:
                raise ValueError()
            prepared = []
            now = int(self.clock())
            for row in rows:
                if not isinstance(row, dict) or set(row) - {"text", "context", "meaning", "model", "review"}:
                    raise ValueError()
                values = [row.get(k, "") for k in ("text", "context", "meaning", "model")]
                validate_text(*values)
                review = row.get("review", {"due": now, "interval": 0, "repetitions": 0, "lapses": 0})
                if not isinstance(review, dict) or set(review) != {"due", "interval", "repetitions", "lapses"}:
                    raise ValueError()
                if any(type(v) is not int or v < 0 for v in review.values()):
                    raise ValueError()
                if review["due"] > 253402300799 or review["interval"] > 3650 or review["repetitions"] > 1000000 or review["lapses"] > review["repetitions"]:
                    raise ValueError()
                prepared.append((values, review))
        except (ValueError, KeyError, TypeError, AttributeError, csv.Error, UnicodeError):
            raise LibraryError("导入格式或条目内容无效；没有写入任何条目。请使用 WordLoom JSON/CSV 格式。") from None
        added = skipped = 0
        with self.conn:
            for (text, context, meaning, model), review in prepared:
                cur = self.conn.execute("""INSERT OR IGNORE INTO entries
                    (id,text,context,meaning,model,fingerprint,created,updated,due,interval,repetitions,lapses)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (uuid4().hex, text.strip(), context.strip(), meaning.strip(), model,
                    fingerprint(text, context), now, now, review["due"], review["interval"], review["repetitions"], review["lapses"]))
                added += cur.rowcount
                skipped += 1 - cur.rowcount
        return added, skipped
