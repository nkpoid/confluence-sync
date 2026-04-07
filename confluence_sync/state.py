from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PageState:
    version: int
    title: str
    space: str
    filename: str


@dataclass
class SyncState:
    last_sync: str = ""
    pages: dict[str, PageState] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> SyncState:
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        pages = {}
        for page_id, pdata in data.get("pages", {}).items():
            pages[page_id] = PageState(
                version=pdata["version"],
                title=pdata["title"],
                space=pdata["space"],
                filename=pdata["filename"],
            )
        return cls(last_sync=data.get("last_sync", ""), pages=pages)

    def save(self, path: Path) -> None:
        data: dict[str, Any] = {
            "last_sync": self.last_sync,
            "pages": {},
        }
        for page_id, ps in self.pages.items():
            data["pages"][page_id] = {
                "version": ps.version,
                "title": ps.title,
                "space": ps.space,
                "filename": ps.filename,
            }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
