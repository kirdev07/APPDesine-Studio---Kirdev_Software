"""Локальный индекс проектов (SQLite). Это кэш: источник правды — файлы .adsproj."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

FILTER_ALL, FILTER_RECENT, FILTER_FAVORITES, FILTER_ARCHIVE = "all", "recent", "favorites", "archive"
SORT_MODIFIED, SORT_TITLE, SORT_CREATED = "modified", "title", "created"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    platforms TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    folder TEXT NOT NULL DEFAULT '',
    favorite INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0,
    missing INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    modified_at TEXT NOT NULL,
    opened_at TEXT NOT NULL DEFAULT '',
    size INTEGER NOT NULL DEFAULT 0,
    screens INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS folders (name TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


@dataclass
class ProjectRecord:
    id: str
    path: str
    title: str
    description: str
    platforms: list[str]
    tags: list[str]
    folder: str
    favorite: bool
    archived: bool
    missing: bool
    created_at: str
    modified_at: str
    opened_at: str
    size: int
    screens: int


class ProjectIndex:
    def __init__(self, db_path: Path | str):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.execute("INSERT OR IGNORE INTO meta VALUES ('index_version', '1')")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    @staticmethod
    def _rec(row: sqlite3.Row) -> ProjectRecord:
        d = dict(row)
        d["platforms"] = json.loads(d["platforms"])
        d["tags"] = json.loads(d["tags"])
        for k in ("favorite", "archived", "missing"):
            d[k] = bool(d[k])
        return ProjectRecord(**d)

    def upsert(self, *, id, path, title, description, platforms, tags, created_at, modified_at, size, screens) -> None:
        path = str(Path(path).resolve())
        with self.conn:
            # Если по этому пути был другой проект (файл перезаписан), убираем старую запись.
            self.conn.execute("DELETE FROM projects WHERE path = ? AND id <> ?", (path, id))
            self.conn.execute(
                """INSERT INTO projects (id, path, title, description, platforms, tags, created_at, modified_at, size, screens)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET path=excluded.path, title=excluded.title,
                     description=excluded.description, platforms=excluded.platforms, tags=excluded.tags,
                     created_at=excluded.created_at, modified_at=excluded.modified_at,
                     size=excluded.size, screens=excluded.screens, missing=0""",
                (id, path, title, description, json.dumps(platforms), json.dumps(tags, ensure_ascii=False),
                 created_at, modified_at, size, screens),
            )

    def get(self, project_id: str) -> ProjectRecord | None:
        row = self.conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return self._rec(row) if row else None

    def remove(self, project_id: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def _set(self, project_id: str, column: str, value) -> None:
        with self.conn:
            self.conn.execute(f"UPDATE projects SET {column} = ? WHERE id = ?", (value, project_id))

    def set_favorite(self, project_id: str, value: bool) -> None:
        self._set(project_id, "favorite", int(value))

    def set_archived(self, project_id: str, value: bool) -> None:
        self._set(project_id, "archived", int(value))

    def set_folder(self, project_id: str, folder: str) -> None:
        self._set(project_id, "folder", folder)

    def mark_missing(self, project_id: str, value: bool = True) -> None:
        self._set(project_id, "missing", int(value))

    def touch_opened(self, project_id: str) -> None:
        self._set(project_id, "opened_at", datetime.now(timezone.utc).isoformat())

    def folders(self) -> list[str]:
        return [r[0] for r in self.conn.execute("SELECT name FROM folders ORDER BY name COLLATE NOCASE")]

    def add_folder(self, name: str) -> None:
        name = name.strip()
        if not name:
            raise ValueError("Пустое имя папки")
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO folders VALUES (?)", (name,))

    def remove_folder(self, name: str) -> None:
        """Удаляет только папку-категорию; проекты остаются, переходят в «без папки»."""
        with self.conn:
            self.conn.execute("UPDATE projects SET folder = '' WHERE folder = ?", (name,))
            self.conn.execute("DELETE FROM folders WHERE name = ?", (name,))

    def query(self, *, filter: str = FILTER_ALL, folder: str | None = None, search: str = "",
              sort: str = SORT_MODIFIED, recent_limit: int = 20) -> list[ProjectRecord]:
        where, args = [], []
        if filter == FILTER_ARCHIVE:
            where.append("archived = 1")
        else:
            where.append("archived = 0")
        if filter == FILTER_FAVORITES:
            where.append("favorite = 1")
        if filter == FILTER_RECENT:
            where.append("opened_at <> ''")
        if folder is not None:
            where.append("folder = ?")
            args.append(folder)
        order = {
            SORT_MODIFIED: "modified_at DESC",
            SORT_CREATED: "created_at DESC",
            SORT_TITLE: "title COLLATE NOCASE ASC",
        }[sort]
        if filter == FILTER_RECENT:
            order = "opened_at DESC"
        sql = f"SELECT * FROM projects WHERE {' AND '.join(where)} ORDER BY {order}"
        records = [self._rec(r) for r in self.conn.execute(sql, args)]
        if search:
            # Поиск в Python: SQLite LOWER() не работает с кириллицей.
            needle = search.casefold()
            records = [r for r in records
                       if needle in r.title.casefold() or needle in r.description.casefold()
                       or any(needle in t.casefold() for t in r.tags)]
        if filter == FILTER_RECENT:
            records = records[:recent_limit]
        return records

    def counts(self, recent_limit: int = 20) -> dict[str, int]:
        return {f: len(self.query(filter=f, recent_limit=recent_limit))
                for f in (FILTER_ALL, FILTER_RECENT, FILTER_FAVORITES, FILTER_ARCHIVE)}

    def folder_counts(self) -> dict[str, int]:
        rows = self.conn.execute("SELECT folder, COUNT(*) FROM projects WHERE archived = 0 GROUP BY folder")
        return {r[0]: r[1] for r in rows}
