from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

DB_FILENAME = ".sync-state.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pages (
    page_id    TEXT PRIMARY KEY,
    version    INTEGER NOT NULL,
    title      TEXT NOT NULL,
    space      TEXT NOT NULL,
    filename   TEXT NOT NULL,
    title_path TEXT NOT NULL DEFAULT ''
);
"""


@dataclass
class PageState:
    version: int
    title: str
    space: str
    filename: str
    title_path: str = ""


class SyncState:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        cols = {
            row[1]
            for row in self._conn.execute("PRAGMA table_info(pages)").fetchall()
        }
        if "title_path" not in cols:
            self._conn.execute(
                "ALTER TABLE pages ADD COLUMN title_path TEXT NOT NULL DEFAULT ''"
            )
            self._conn.commit()

    @property
    def last_sync(self) -> str:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'last_sync'"
        ).fetchone()
        return row[0] if row else ""

    @last_sync.setter
    def last_sync(self, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_sync', ?)",
            (value,),
        )
        self._conn.commit()

    @property
    def page_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM pages").fetchone()
        return row[0] if row else 0

    def get_page(self, page_id: str) -> PageState | None:
        row = self._conn.execute(
            "SELECT version, title, space, filename, title_path FROM pages WHERE page_id = ?",
            (page_id,),
        ).fetchone()
        if row is None:
            return None
        return PageState(version=row[0], title=row[1], space=row[2], filename=row[3], title_path=row[4])

    def has_page(self, page_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM pages WHERE page_id = ?", (page_id,)
        ).fetchone()
        return row is not None

    def upsert_page(self, page_id: str, ps: PageState) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO pages (page_id, version, title, space, filename, title_path) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (page_id, ps.version, ps.title, ps.space, ps.filename, ps.title_path),
        )
        self._conn.commit()

    def delete_page(self, page_id: str) -> None:
        self._conn.execute("DELETE FROM pages WHERE page_id = ?", (page_id,))
        self._conn.commit()

    def all_pages(self) -> dict[str, PageState]:
        rows = self._conn.execute(
            "SELECT page_id, version, title, space, filename, title_path FROM pages"
        ).fetchall()
        return {
            row[0]: PageState(version=row[1], title=row[2], space=row[3], filename=row[4], title_path=row[5])
            for row in rows
        }

    def close(self) -> None:
        self._conn.close()
