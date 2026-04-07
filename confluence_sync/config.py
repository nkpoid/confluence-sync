from __future__ import annotations

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
    pat: str = ""
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

        config = cls(
            base_url=data.get("base_url", "").rstrip("/"),
            pat=data.get("pat", ""),
            output_dir=data.get("output_dir", "./confluence-export"),
            spaces=data.get("spaces", []),
            sync=sync_config,
        )

        if not config.base_url:
            print(
                f"エラー: base_url が設定されていません。\n"
                f"{path} に base_url を追加してください。",
                file=sys.stderr,
            )
            raise SystemExit(1)

        if not config.pat:
            print(
                f"エラー: pat が設定されていません。\n"
                f"{path} に pat を追加してください。\n"
                "Personal Access Token の作成手順:\n"
                "  プロフィール → Personal Access Tokens → Create token",
                file=sys.stderr,
            )
            raise SystemExit(1)

        return config
