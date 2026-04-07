from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import tomli


@dataclass
class SyncConfig:
    include_attachments: bool = True
    attachment_dir: str = "_attachments"


@dataclass
class Config:
    base_url: str = ""
    output_dir: str = "./confluence-export"
    spaces: list[str] = field(default_factory=list)
    sync: SyncConfig = field(default_factory=SyncConfig)

    @classmethod
    def load(cls, path: Path) -> Config:
        with open(path, "rb") as f:
            data = tomli.load(f)

        sync_data = data.get("sync", {})
        sync_config = SyncConfig(
            include_attachments=sync_data.get("include_attachments", True),
            attachment_dir=sync_data.get("attachment_dir", "_attachments"),
        )

        return cls(
            base_url=data.get("base_url", "").rstrip("/"),
            output_dir=data.get("output_dir", "./confluence-export"),
            spaces=data.get("spaces", []),
            sync=sync_config,
        )

    def get_pat(self) -> str:
        pat = os.environ.get("CONFLUENCE_PAT", "")
        if not pat:
            print(
                "エラー: 環境変数 CONFLUENCE_PAT が設定されていません。\n"
                "Confluence Data Center で Personal Access Token を作成してください:\n"
                "  プロフィール → Personal Access Tokens → Create token\n"
                "作成後: export CONFLUENCE_PAT='your-token'",
                file=sys.stderr,
            )
            raise SystemExit(1)
        return pat
