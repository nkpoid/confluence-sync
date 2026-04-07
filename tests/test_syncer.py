import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import responses

from confluence_sync.config import Config, SyncConfig
from confluence_sync.state import PageState, SyncState
from confluence_sync.syncer import (
    build_cql,
    extract_page_info,
    make_filename,
    pull,
    rewrite_attachment_paths,
)


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
        assert 'lastModified >= "2025-04-01T10:00:00Z"' in cql

    def test_full_ignores_last_sync(self):
        cql = build_cql([], "2025-04-01T10:00:00Z", full=True)
        assert "lastModified >=" not in cql

    def test_spaces_and_last_sync(self):
        cql = build_cql(["DEV"], "2025-04-01T00:00:00Z", full=False)
        assert "type=page" in cql
        assert 'space in ("DEV")' in cql
        assert 'lastModified >= "2025-04-01T00:00:00Z"' in cql
        assert "order by lastModified desc" in cql


class TestMakeFilename:
    def test_basic(self):
        assert make_filename("12345", "API Design") == "12345-api-design.md"

    def test_special_characters(self):
        result = make_filename("99", "Hello / World: Test!")
        assert result.startswith("99-")
        assert result.endswith(".md")
        # slug should not contain special chars
        assert "/" not in result
        assert ":" not in result

    def test_long_title_truncated(self):
        title = "A" * 200
        result = make_filename("1", title)
        # max_length=80 for slug + "1-" prefix + ".md" suffix
        assert len(result) <= 90

    def test_japanese_title(self):
        result = make_filename("42", "設計ドキュメント")
        assert result.startswith("42-")
        assert result.endswith(".md")


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
    def test_rewrite(self):
        md = "![img](/rest/api/content/123/child/attachment/456/data/diagram.png)"
        result = rewrite_attachment_paths(md, "123", "_attachments")
        assert "_attachments/123/" in result
        assert "/rest/api/" not in result


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

    @patch("confluence_sync.syncer.ConfluenceAPI")
    def test_pull_new_page(self, mock_api_cls, tmp_path):
        output = str(tmp_path / "export")
        config = self._make_config(output)

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_api.search_pages.return_value = [self._make_page()]

        result = pull(config)

        assert result.new == 1
        assert result.errors == 0

        # ファイルが作成されたか
        md_files = list((tmp_path / "export" / "DEV").glob("*.md"))
        assert len(md_files) == 1
        assert "12345" in md_files[0].name

        # sync-state が更新されたか
        state_path = tmp_path / "export" / ".sync-state.json"
        assert state_path.exists()
        state_data = json.loads(state_path.read_text())
        assert "12345" in state_data["pages"]

    @patch("confluence_sync.syncer.ConfluenceAPI")
    def test_pull_updates_existing(self, mock_api_cls, tmp_path):
        output = str(tmp_path / "export")
        config = self._make_config(output)

        # 既存のsync-stateを作成
        state = SyncState(
            last_sync="2025-04-01T00:00:00Z",
            pages={
                "12345": PageState(
                    version=1,
                    title="Test Page",
                    space="DEV",
                    filename="12345-test-page.md",
                )
            },
        )
        state_path = Path(output) / ".sync-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state.save(state_path)

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        page = self._make_page()
        page["version"]["number"] = 2
        mock_api.search_pages.return_value = [page]

        result = pull(config)

        assert result.updated == 1
        assert result.new == 0

    @patch("confluence_sync.syncer.ConfluenceAPI")
    def test_pull_renames_on_title_change(self, mock_api_cls, tmp_path):
        output = str(tmp_path / "export")
        config = self._make_config(output)

        # 既存のファイルとstateを作成
        dev_dir = Path(output) / "DEV"
        dev_dir.mkdir(parents=True)
        old_file = dev_dir / "12345-old-title.md"
        old_file.write_text("old content")

        state = SyncState(
            last_sync="2025-04-01T00:00:00Z",
            pages={
                "12345": PageState(
                    version=1,
                    title="Old Title",
                    space="DEV",
                    filename="12345-old-title.md",
                )
            },
        )
        state_path = Path(output) / ".sync-state.json"
        state.save(state_path)

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_api.search_pages.return_value = [
            self._make_page("12345", "New Title")
        ]

        result = pull(config)

        # 旧ファイルが削除されたか
        assert not old_file.exists()
        # 新ファイルが作成されたか
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
