from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from slugify import slugify

from .api import ConfluenceAPI
from .config import Config
from .converter import build_page_markdown
from .state import DB_FILENAME, PageState, SyncState

console = Console(stderr=True)


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


def build_page_relpath(ancestors: list[dict], page_id: str, title: str) -> str:
    """ancestors からスペースディレクトリ内の相対パスを構築する。

    例: ancestors=[{id:"100",title:"Arch"},{id:"300",title:"DB"}], page_id="400", title="Schema"
    → "100-arch/300-db/400-schema.md"
    """
    parts: list[str] = []
    for anc in ancestors:
        anc_slug = slugify(anc.get("title", ""), max_length=80)
        parts.append(f"{anc['id']}-{anc_slug}")
    filename = make_filename(page_id, title)
    if parts:
        return str(Path(*parts) / filename)
    return filename


def extract_page_info(
    page: dict,
) -> tuple[str, str, str, int, str, list[str], str]:
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
    md_content: str, page_id: str, attachment_dir: str, depth: int = 0
) -> str:
    """MD内の添付ファイルパスを相対パスに書き換える。"""
    prefix = "../" * depth if depth > 0 else ""
    base = f"{prefix}{attachment_dir}/{page_id}/"

    pattern = r'(/rest/api/content/[^/]+/child/attachment[^\s\)\"]*)'

    def _replace(match: re.Match) -> str:
        url = match.group(1)
        parts = url.rstrip("/").split("/")
        filename = parts[-1] if parts else "attachment"
        return f"{base}{filename}"

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
        try:
            data = api.download_attachment(download_path)
            dest.write_bytes(data)
            count += 1
        except Exception:
            pass
    return count


def _to_cql_date(iso_date: str) -> str:
    """ISO 8601 日付を CQL 互換フォーマットに変換し、1分加算する。

    CQLは分単位精度のため、同一分のページが >=  で再取得されるのを防ぐ。
    sync済みページは全てこの分以前に更新されているので、1分進めても取りこぼさない。
    """
    from datetime import datetime, timedelta

    dt = datetime.fromisoformat(iso_date)
    dt += timedelta(minutes=1)
    return dt.strftime("%Y-%m-%d %H:%M")


def build_cql(spaces: list[str], last_sync: str | None, full: bool) -> str:
    """同期用CQLクエリを構築する。"""
    conditions = ["type=page"]
    if spaces:
        space_list = ",".join(f'"{s}"' for s in spaces)
        conditions.append(f"space in ({space_list})")
    if last_sync and not full:
        cql_date = _to_cql_date(last_sync)
        conditions.append(f'lastModified >= "{cql_date}"')
    cql = " and ".join(conditions) + " order by lastModified desc"
    return cql


def pull(config: Config, full: bool = False, detect_deletes: bool = False) -> SyncResult:
    """メイン同期処理。"""
    api = ConfluenceAPI(config)
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    state = SyncState(output_dir / DB_FILENAME)

    last_sync = None if full else (state.last_sync or None)
    cql = build_cql(config.spaces, last_sync, full)

    # ページ一覧取得（スピナー表示）
    with console.status(
        f"Fetching changes since {last_sync}..." if last_sync else "Fetching all pages..."
    ):
        pages = list(api.search_pages(cql))

    console.print(f"Found {len(pages)} {'updated ' if last_sync else ''}pages\n")

    result = SyncResult()
    total_attachments = 0
    max_last_modified = state.last_sync or ""

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

                ancestors = api.get_ancestors(page_id)
                title_path = " / ".join(
                    [a["title"] for a in ancestors] + [title]
                )

                space_dir = output_dir / space_key
                space_dir.mkdir(parents=True, exist_ok=True)

                relpath = build_page_relpath(ancestors, page_id, title)

                # タイトル or 階層変更の検知 → 旧ファイル削除
                old_state = state.get_page(page_id)
                if old_state and old_state.filename != relpath:
                    old_path = output_dir / old_state.space / old_state.filename
                    if old_path.exists():
                        old_path.unlink()

                is_new = not state.has_page(page_id)

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

                # 添付画像パスを相対パスに書き換え（ツリーの深さを考慮）
                if config.sync.include_attachments:
                    depth = len(ancestors)
                    md_content = rewrite_attachment_paths(
                        md_content, page_id, config.sync.attachment_dir, depth
                    )

                filepath = space_dir / relpath
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(md_content, encoding="utf-8")

                # sync-state をページ単位で更新（中断耐性）
                state.upsert_page(page_id, PageState(
                    version=version,
                    title=title,
                    space=space_key,
                    filename=relpath,
                    title_path=title_path,
                ))

                if last_modified > max_last_modified:
                    max_last_modified = last_modified

                status = "new" if is_new else "updated"
                if is_new:
                    result.new += 1
                else:
                    result.updated += 1

                page_url = f"{config.base_url}/spaces/{space_key}/pages/{page_id}"
                progress.console.print(
                    f"  [green]✓[/green] [link={page_url}]{space_key} / {title_path}[/link] ({status})"
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
        for page_id, ps in state.all_pages().items():
            if not api.page_exists(page_id):
                trash_dir.mkdir(parents=True, exist_ok=True)
                src = output_dir / ps.space / ps.filename
                if src.exists():
                    shutil.move(str(src), str(trash_dir / Path(ps.filename).name))
                state.delete_page(page_id)
                result.deleted += 1
                display = ps.title_path or ps.title
                page_url = f"{config.base_url}/spaces/{ps.space}/pages/{page_id}"
                console.print(f"  [yellow]⊘[/yellow] [link={page_url}]{ps.space} / {display}[/link] (deleted)")

    # 最終state更新（Confluenceが返すタイムスタンプの最大値を使う）
    if max_last_modified:
        state.last_sync = max_last_modified

    state.close()

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

    state = SyncState(output_dir / DB_FILENAME)

    if not state.last_sync:
        console.print("まだ同期が実行されていません。`confluence-sync pull` を実行してください。")
        state.close()
        return

    cql = build_cql(config.spaces, state.last_sync, full=False)
    with console.status("Checking for changes..."):
        pages = list(api.search_pages(cql, expand="version"))

    console.print(f"Last sync: {state.last_sync}")
    console.print(f"Synced pages: {state.page_count}")
    console.print(f"Changed since last sync: {len(pages)}")
    state.close()
