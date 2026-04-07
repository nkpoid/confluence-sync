from __future__ import annotations

from pathlib import Path

import click
import tomli_w
from rich.console import Console
from rich.table import Table

from .api import ConfluenceAPI
from .config import Config

CONFIG_FILE = ".confluence-sync.toml"
console = Console()


def load_config() -> Config:
    path = Path(CONFIG_FILE)
    if not path.exists():
        console.print(
            f"[red]設定ファイル {CONFIG_FILE} が見つかりません。[/red]\n"
            "`confluence-sync init` を実行して設定ファイルを作成してください。"
        )
        raise SystemExit(1)
    return Config.load(path)


@click.group()
def main() -> None:
    """Confluence → Markdown 差分同期ツール"""
    pass


@main.command()
def init() -> None:
    """設定ファイル(.confluence-sync.toml)を対話的に生成する。"""
    path = Path(CONFIG_FILE)
    if path.exists():
        if not click.confirm(f"{CONFIG_FILE} は既に存在します。上書きしますか？"):
            return

    base_url = click.prompt("Confluence Base URL", type=str)
    base_url = base_url.rstrip("/")

    pat = click.prompt("Personal Access Token (PAT)", type=str, hide_input=True)

    output_dir = click.prompt("出力ディレクトリ", default="./confluence-export", type=str)

    spaces_input = click.prompt(
        "対象スペース (カンマ区切り、空欄で全スペース)", default="", type=str
    )
    spaces = [s.strip() for s in spaces_input.split(",") if s.strip()] if spaces_input else []

    include_attachments = click.confirm("添付ファイルもダウンロードしますか？", default=True)
    attachment_dir = "_attachments"
    if include_attachments:
        attachment_dir = click.prompt("添付ファイルディレクトリ名", default="_attachments", type=str)

    data = {
        "base_url": base_url,
        "pat": pat,
        "output_dir": output_dir,
        "spaces": spaces,
        "sync": {
            "include_attachments": include_attachments,
            "attachment_dir": attachment_dir,
        },
    }

    path.write_text(tomli_w.dumps(data), encoding="utf-8")
    console.print(f"\n[green]✓[/green] {CONFIG_FILE} を作成しました。")
    console.print("このファイルは .gitignore に含まれています。")


@main.command()
@click.option("--full", is_flag=True, help="強制全件取得")
@click.option("--detect-deletes", is_flag=True, help="削除されたページを検知する")
def pull(full: bool, detect_deletes: bool) -> None:
    """差分同期を実行する（初回は全件取得）。"""
    from .syncer import pull as do_pull

    config = load_config()
    do_pull(config, full=full, detect_deletes=detect_deletes)


@main.command()
def status() -> None:
    """前回同期からの変更件数を表示する。"""
    from .syncer import get_status

    config = load_config()
    get_status(config)


@main.command("list-spaces")
def list_spaces() -> None:
    """アクセス可能なスペース一覧を表示する。"""
    config = load_config()
    api = ConfluenceAPI(config)

    spaces = api.get_spaces()

    table = Table(title="Confluence Spaces")
    table.add_column("Key", style="cyan")
    table.add_column("Name")
    table.add_column("Type")

    for space in spaces:
        table.add_row(space["key"], space["name"], space.get("type", ""))

    console.print(table)
    console.print(f"\n合計: {len(spaces)} スペース")
