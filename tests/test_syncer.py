from pathlib import Path
from unittest.mock import MagicMock, patch

from confluence_sync.config import Config, SyncConfig
from confluence_sync.state import DB_FILENAME, PageState, SyncState
from confluence_sync.syncer import (
    _to_cql_date,
    build_cql,
    build_page_relpath,
    extract_page_info,
    make_filename,
    pull,
    rewrite_attachment_paths,
)


class TestToCqlDate:
    def test_iso_to_cql(self):
        assert _to_cql_date("2026-04-07T10:34:06Z") == "2026-04-07 10:34"

    def test_already_short(self):
        assert _to_cql_date("2026-04-07T10:34") == "2026-04-07 10:34"


class TestBuildCql:
    def test_no_spaces_no_last_sync(self):
        cql = build_cql([], None, full=False)
        assert cql == "type=page order by lastModified desc"

    def test_with_spaces(self):
        cql = build_cql(["DEV", "OPS"], None, full=False)
        assert 'space in ("DEV","OPS")' in cql
        assert "type=page" in cql

    def test_with_last_sync(self):
        cql = build_cql([], "2025-04-01T10:00:00Z", full=False)
        assert 'lastModified >= "2025-04-01 10:00"' in cql

    def test_full_ignores_last_sync(self):
        cql = build_cql([], "2025-04-01T10:00:00Z", full=True)
        assert "lastModified >=" not in cql

    def test_spaces_and_last_sync(self):
        cql = build_cql(["DEV"], "2025-04-01T00:00:00Z", full=False)
        assert "type=page" in cql
        assert 'space in ("DEV")' in cql
        assert 'lastModified >= "2025-04-01 00:00"' in cql
        assert "order by lastModified desc" in cql


class TestMakeFilename:
    def test_basic(self):
        assert make_filename("12345", "API Design") == "12345-api-design.md"

    def test_special_characters(self):
        result = make_filename("99", "Hello / World: Test!")
        assert result.startswith("99-")
        assert result.endswith(".md")
        assert "/" not in result
        assert ":" not in result

    def test_long_title_truncated(self):
        title = "A" * 200
        result = make_filename("1", title)
        assert len(result) <= 90

    def test_japanese_title(self):
        result = make_filename("42", "設計ドキュメント")
        assert result.startswith("42-")
        assert result.endswith(".md")


class TestBuildPageRelpath:
    def test_no_ancestors(self):
        result = build_page_relpath([], "100", "Root Page")
        assert result == "100-root-page.md"

    def test_single_ancestor(self):
        ancestors = [{"id": "10", "title": "Parent"}]
        result = build_page_relpath(ancestors, "20", "Child")
        assert result == "10-parent/20-child.md"

    def test_multiple_ancestors(self):
        ancestors = [
            {"id": "1", "title": "Grandparent"},
            {"id": "2", "title": "Parent"},
        ]
        result = build_page_relpath(ancestors, "3", "Leaf")
        assert result == "1-grandparent/2-parent/3-leaf.md"


class TestExtractPageInfo:
    def test_extract(self):
        page = {
            "id": "12345",
            "title": "Test Page",
            "space": {"key": "DEV"},
            "version": {"number": 3, "when": "2025-04-01T10:30:00Z"},
            "metadata": {
                "labels": {"results": [{"name": "api"}, {"name": "design"}]}
            },
            "body": {"storage": {"value": "<p>Hello</p>"}},
        }
        page_id, title, space_key, version, last_modified, labels, body_html = (
            extract_page_info(page)
        )
        assert page_id == "12345"
        assert title == "Test Page"
        assert space_key == "DEV"
        assert version == 3
        assert last_modified == "2025-04-01T10:30:00Z"
        assert labels == ["api", "design"]
        assert body_html == "<p>Hello</p>"

    def test_extract_no_labels(self):
        page = {
            "id": "1",
            "title": "T",
            "space": {"key": "S"},
            "version": {"number": 1, "when": "2025-01-01T00:00:00Z"},
            "metadata": {},
            "body": {"storage": {"value": ""}},
        }
        _, _, _, _, _, labels, _ = extract_page_info(page)
        assert labels == []


class TestRewriteAttachmentPaths:
    def test_rewrite_depth_0(self):
        md = "![img](/rest/api/content/123/child/attachment/456/data/diagram.png)"
        result = rewrite_attachment_paths(md, "123", "_attachments", depth=0)
        assert result == "![img](_attachments/123/diagram.png)"

    def test_rewrite_depth_1(self):
        md = "![img](/rest/api/content/123/child/attachment/456/data/diagram.png)"
        result = rewrite_attachment_paths(md, "123", "_attachments", depth=1)
        assert result == "![img](../_attachments/123/diagram.png)"

    def test_rewrite_depth_2(self):
        md = "![img](/rest/api/content/123/child/attachment/456/data/diagram.png)"
        result = rewrite_attachment_paths(md, "123", "_attachments", depth=2)
        assert result == "![img](../../_attachments/123/diagram.png)"


class TestPull:
    def _make_config(self, output_dir: str) -> Config:
        return Config(
            base_url="https://confluence.example.com",
            output_dir=output_dir,
            spaces=["DEV"],
            sync=SyncConfig(include_attachments=False),
        )

    def _make_page(self, page_id: str = "12345", title: str = "Test Page") -> dict:
        return {
            "id": page_id,
            "title": title,
            "space": {"key": "DEV"},
            "version": {"number": 1, "when": "2025-04-01T10:30:00Z"},
            "metadata": {"labels": {"results": []}},
            "body": {"storage": {"value": "<p>Hello world</p>"}},
        }

    def _seed_state(self, output_dir: str, last_sync: str, pages: dict[str, PageState]) -> None:
        """テスト用に既存の sync-state DB を作成する。"""
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        state = SyncState(output / DB_FILENAME)
        state.last_sync = last_sync
        for page_id, ps in pages.items():
            state.upsert_page(page_id, ps)
        state.close()

    @patch("confluence_sync.syncer.ConfluenceAPI")
    def test_pull_new_page(self, mock_api_cls, tmp_path):
        output = str(tmp_path / "export")
        config = self._make_config(output)

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_api.search_pages.return_value = [self._make_page()]
        mock_api.get_ancestors.return_value = []

        result = pull(config)

        assert result.new == 1
        assert result.errors == 0

        md_files = list((tmp_path / "export" / "DEV").glob("*.md"))
        assert len(md_files) == 1
        assert "12345" in md_files[0].name

        # DB に保存されたか確認
        state = SyncState(tmp_path / "export" / DB_FILENAME)
        assert state.has_page("12345")
        state.close()

    @patch("confluence_sync.syncer.ConfluenceAPI")
    def test_pull_nested_page(self, mock_api_cls, tmp_path):
        output = str(tmp_path / "export")
        config = self._make_config(output)

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_api.search_pages.return_value = [self._make_page("200", "Child Page")]
        mock_api.get_ancestors.return_value = [{"id": "100", "title": "Parent Page"}]

        result = pull(config)

        assert result.new == 1
        child_path = tmp_path / "export" / "DEV" / "100-parent-page" / "200-child-page.md"
        assert child_path.exists()

        state = SyncState(tmp_path / "export" / DB_FILENAME)
        ps = state.get_page("200")
        assert ps is not None
        assert ps.filename == "100-parent-page/200-child-page.md"
        state.close()

    @patch("confluence_sync.syncer.ConfluenceAPI")
    def test_pull_updates_existing(self, mock_api_cls, tmp_path):
        output = str(tmp_path / "export")
        config = self._make_config(output)

        self._seed_state(output, "2025-04-01T00:00:00Z", {
            "12345": PageState(version=1, title="Test Page", space="DEV", filename="12345-test-page.md"),
        })

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        page = self._make_page()
        page["version"]["number"] = 2
        mock_api.search_pages.return_value = [page]
        mock_api.get_ancestors.return_value = []

        result = pull(config)

        assert result.updated == 1
        assert result.new == 0

    @patch("confluence_sync.syncer.ConfluenceAPI")
    def test_pull_renames_on_title_change(self, mock_api_cls, tmp_path):
        output = str(tmp_path / "export")
        config = self._make_config(output)

        dev_dir = Path(output) / "DEV"
        dev_dir.mkdir(parents=True)
        old_file = dev_dir / "12345-old-title.md"
        old_file.write_text("old content")

        self._seed_state(output, "2025-04-01T00:00:00Z", {
            "12345": PageState(version=1, title="Old Title", space="DEV", filename="12345-old-title.md"),
        })

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_api.search_pages.return_value = [
            self._make_page("12345", "New Title")
        ]
        mock_api.get_ancestors.return_value = []

        result = pull(config)

        assert not old_file.exists()
        new_files = list(dev_dir.glob("12345-*.md"))
        assert len(new_files) == 1
        assert "new-title" in new_files[0].name

    @patch("confluence_sync.syncer.ConfluenceAPI")
    def test_pull_empty_result(self, mock_api_cls, tmp_path):
        output = str(tmp_path / "export")
        config = self._make_config(output)

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_api.search_pages.return_value = []

        result = pull(config)

        assert result.new == 0
        assert result.updated == 0
        assert result.errors == 0
