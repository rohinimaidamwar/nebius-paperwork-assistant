"""Local SQLite memory. Nothing here leaves the machine.

Stores the structured explanation of each document (not the raw text) so the
assistant can remember deadlines and answer follow-up questions across sessions.
The saved summaries are restored (they contain the real names and identifiers),
so the database file itself is sensitive. It also remembers which names you asked
to hide, so `ask` can keep masking them. `forget` deletes one document or everything.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    doc_type TEXT, title TEXT, summary TEXT, data_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deadlines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    due_date TEXT NOT NULL, what TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS hidden_names (name TEXT PRIMARY KEY);
"""

# Common words that would otherwise make every document "match" every question.
_STOPWORDS = {
    "the", "and", "for", "what", "when", "which", "who", "how", "with", "from", "that", "this",
    "are", "was", "were", "you", "your", "can", "have", "has", "does", "did", "not", "about", "any",
}

def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"\w+", text.lower()) if len(t) > 2 and t not in _STOPWORDS}

class Memory:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA secure_delete = ON")  # overwrite deleted rows instead of leaving them in the file
        self.db.executescript(SCHEMA)

    def add(self, result: dict[str, Any], now: datetime | None = None) -> int:
        now = now or datetime.now()
        cur = self.db.execute(
            "INSERT INTO documents (created_at, doc_type, title, summary, data_json) VALUES (?,?,?,?,?)",
            (now.isoformat(timespec="seconds"), result.get("doc_type"), result.get("title"),
             result.get("plain_summary"), json.dumps(result, ensure_ascii=False)))
        doc_id = cur.lastrowid
        for d in result.get("deadlines", []):
            if d.get("date"):
                self.db.execute("INSERT INTO deadlines (doc_id, due_date, what) VALUES (?,?,?)",
                                (doc_id, d["date"], d.get("what", "")))
        self.db.commit()
        return doc_id

    def add_hidden(self, names: list[str]) -> None:
        for n in names:
            if n and n.strip():
                self.db.execute("INSERT OR IGNORE INTO hidden_names (name) VALUES (?)", (n.strip(),))
        self.db.commit()

    def hidden_names(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT name FROM hidden_names ORDER BY name")]

    def upcoming(self, today: date | None = None, days: int = 30) -> list[dict[str, Any]]:
        today = today or date.today()
        end = today + timedelta(days=days)
        rows = self.db.execute(
            "SELECT d.due_date, d.what, doc.id, doc.title FROM deadlines d JOIN documents doc ON doc.id = d.doc_id "
            "WHERE d.due_date >= ? AND d.due_date <= ? ORDER BY d.due_date",
            (today.isoformat(), end.isoformat())).fetchall()
        return [{"date": r[0], "what": r[1], "doc_id": r[2], "title": r[3]} for r in rows]

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        q = _tokens(query)
        scored = []
        for doc_id, data_json in self.db.execute("SELECT id, data_json FROM documents"):
            data = json.loads(data_json)
            blob = " ".join([data.get("title", ""), data.get("plain_summary", ""), *data.get("key_points", [])])
            score = len(q & _tokens(blob))
            if score:
                scored.append((score, doc_id, data))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        return [{"doc_id": i, **d} for _, i, d in scored[:limit]]

    def all_documents(self) -> list[dict[str, Any]]:
        return [{"doc_id": i, **json.loads(j)} for i, j in
                self.db.execute("SELECT id, data_json FROM documents ORDER BY id DESC")]

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def forget(self, doc_id: int | None = None) -> int:
        """Delete one document (and its deadlines), or everything (and remembered names) when doc_id is None."""
        before = self.count()
        if doc_id is None:
            self.db.execute("DELETE FROM documents")
            self.db.execute("DELETE FROM hidden_names")
        else:
            self.db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        self.db.commit()
        self.db.execute("VACUUM")  # shrink the file so deleted data is not left behind
        return before - self.count()
