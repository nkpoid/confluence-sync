from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from slugify import slugify

from .api import ConfluenceAPI
from .config import Config
from .converter import build_page_markdown
from .state import PageState, SyncState

console = Console()


@dataclass
class SyncResult:
    new: int = 0
    updated: int = 0
    deleted: int = 0
    errors: int = 0
    error_pages: list[str] = field(default_factory=list)


def make_filename(page_id: str, title: str) -> str:
    slug = slugify(title, max_length=80)
    return f"{page_id}-{slug}.md"


def extract_page_info(page: dict) -> tuple[str, str, str, int, str, list[str], str]:
    """APIレスポンスからページ情報を抽出する。"""
    page_id = page["id"]
    title = page["title"]
    space_key = page["space"]["key"]
    version = page["version"]["number"]
    last_modified = page["version"]["when"]
    labels = [
        lbl["name"]
        for lbl in page.get("metadata", {}).get("labels", {}).get("results", [])
    ]
    body_html = page.get("body", {}).get("storage", {}).get("value", "")
    return page_id, title, space_key, version, last_modified, labels, body_html


def rewrite_attachment_paths(
    md_content: str, page_id: str, attachment_dir: str
) -> str:
    """MD内の添付ファイルパスを相対パスに書き換える。"""
    pattern = r'(/rest/api/content/[^/]+/child/attachment[^\s\)\"]*)'
    replacement = f"{attachment_dir}/{page_id}/"

    def _replace(match: re.Match) -> str:
        url = match.group(1)
        # URLの末尾からファイル名を取得
        parts = url.rstrip("/").split("/")
        filename = parts[-1] if parts else "attachment"
        return f"{replacement}{filename}"

    return re.sub(pattern, _replace, md_content)


def sync_attachments(
    api: ConfluenceAPI,
    page_id: str,
    space_dir: Path,
    attachment_dir_name: str,
) -> int:
    """ページの添付ファイルをダウンロードする。ダウンロード数を返す。"""
    attachments = api.get_attachments(page_id)
    if not attachments:
        return 0

    att_dir = space_dir / attachment_dir_name / page_id
    att_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for att in attachments:
        title = att["title"]
        download_path = att.get("_links", {}).get("download", "")
        if not download_path:
            continue
        dest = att_dir / title
        if dest.exists():
            # 簡易チェック: サイズが同じならスキップ
            existing_size = dest.stat().st_size
            # ヘッダーだけ取れないので常にDL（差分同期の対象ページなので更新あり前提）
            pass
        try:
            data = api.download_attachment(download_path)
            dest.write_bytes(data)
            count += 1
        except Exception:
            pass  # 添付ファイルエラーは静かにスキップ
    return count


def build_cql(spaces: list[str], last_sync: str | None, full: bool) -> str:
    """同期用CQLクエリを構築する。"""
    conditions = ["type=page"]
    if spaces:
        space_list = ",".join(f'"{s}"' for s in spaces)
        conditions.append(f"space in ({space_list})")
    if last_sync and not full:
        conditions.append(f'lastModified >= "{last_sync}"')
    cql = " and ".join(conditions) + " order by lastModified desc"
    return cql


def pull(config: Config, full: bool = False, detect_deletes: bool = False) -> SyncResult:
    """メイン同期処理。"""
    api = ConfluenceAPI(config)
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    state_path = output_dir / ".sync-state.json"
    state = SyncState.load(state_path)

    last_sync = None if full else (state.last_sync or None)

    cql = build_cql(config.spaces, last_sync, full)

    if last_sync and not full:
        console.print(f"Fetching changes since {last_sync}...")
    else:
        console.print("Fetching all pages...")

    # ページ一覧取得
    pages = list(api.search_pages(cql))
    console.print(f"Found {len(pages)} {'updated ' if last_sync else ''}pages\n")

    result = SyncResult()
    total_attachments = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Syncing pages", total=len(pages))

        for page in pages:
            try:
                page_id, title, space_key, version, last_modified, labels, body_html = (
                    extract_page_info(page)
                )

                space_dir = output_dir / space_key
                space_dir.mkdir(parents=True, exist_ok=True)

                filename = make_filename(page_id, title)

                # タイトル変更の検知 → 旧ファイル削除
                old_state = state.pages.get(page_id)
                if old_state and old_state.filename != filename:
                    old_path = output_dir / old_state.space / old_state.filename
                    if old_path.exists():
                        old_path.unlink()

                is_new = page_id not in state.pages

                md_content = build_page_markdown(
                    page_id=page_id,
                    title=title,
                    space_key=space_key,
                    base_url=config.base_url,
                    version=version,
                    last_modified=last_modified,
                    labels=labels,
                    body_html=body_html,
                )

                # 添付画像パス書き換え
                if config.sync.include_attachments:
                    md_content = rewrite_attachment_paths(
                        md_content, page_id, config.sync.attachment_dir
                    )

                filepath = space_dir / filename
                filepath.write_text(md_content, encoding="utf-8")

                # sync-state をページ単位で更新（中断耐性）
                state.pages[page_id] = PageState(
                    version=version,
                    title=title,
                    space=space_key,
                    filename=filename,
                )
                state.save(state_path)

                status = "new" if is_new else "updated"
                if is_new:
                    result.new += 1
                else:
                    result.updated += 1

                progress.console.print(
                    f"  [green]✓[/green] {space_key}/{filename} ({status})"
                )

            except Exception as e:
                result.errors += 1
                pid = page.get("id", "unknown")
                result.error_pages.append(pid)
                progress.console.print(
                    f"  [red]✗[/red] {pid} (skipped - {e})"
                )

            progress.advance(task)

    # 添付ファイルダウンロード
    if config.sync.include_attachments and pages:
        attachment_pages = [
            (p.get("id", ""), p.get("space", {}).get("key", ""))
            for p in pages
        ]
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            att_task = progress.add_task(
                "Downloading attachments", total=len(attachment_pages)
            )
            for page_id, space_key in attachment_pages:
                if page_id and space_key:
                    space_dir = output_dir / space_key
                    try:
                        count = sync_attachments(
                            api, page_id, space_dir, config.sync.attachment_dir
                        )
                        total_attachments += count
                    except Exception:
                        pass
                progress.advance(att_task)

    # 削除検知
    if detect_deletes:
        console.print("\nChecking for deleted pages...")
        trash_dir = output_dir / ".trash"
        for page_id, ps in list(state.pages.items()):
            if not api.page_exists(page_id):
                # .trash に移動
                trash_dir.mkdir(parents=True, exist_ok=True)
                src = output_dir / ps.space / ps.filename
                if src.exists():
                    shutil.move(str(src), str(trash_dir / ps.filename))
                del state.pages[page_id]
                result.deleted += 1
                console.print(f"  [yellow]⊘[/yellow] {ps.space}/{ps.filename} (deleted)")

    # 最終state更新
    state.last_sync = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state.save(state_path)

    synced = result.new + result.updated
    console.print(
        f"\nDone. {synced} synced, {result.errors} error(s), {result.deleted} deleted."
    )
    if total_attachments:
        console.print(f"Attachments downloaded: {total_attachments}")

    return result


def get_status(config: Config) -> None:
    """前回同期からの変更件数を表示する。"""
    api = ConfluenceAPI(config)
    output_dir = Path(config.output_dir)
    state_path = output_dir / ".sync-state.json"
    state = SyncState.load(state_path)

    if not state.last_sync:
        console.print("まだ同期が実行されていません。`confluence-sync pull` を実行してください。")
        return

    cql = build_cql(config.spaces, state.last_sync, full=False)
    pages = list(api.search_pages(cql))

    console.print(f"Last sync: {state.last_sync}")
    console.print(f"Synced pages: {len(state.pages)}")
    console.print(f"Changed since last sync: {len(pages)}")
