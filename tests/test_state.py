import json
from pathlib import Path

from confluence_sync.state import PageState, SyncState


class TestSyncState:
    def test_load_nonexistent(self, tmp_path):
        state = SyncState.load(tmp_path / "nonexistent.json")
        assert state.last_sync == ""
        assert state.pages == {}

    def test_save_and_load(self, tmp_path):
        state_path = tmp_path / ".sync-state.json"
        state = SyncState(
            last_sync="2025-04-01T10:00:00Z",
            pages={
                "123": PageState(
                    version=5,
                    title="Test Page",
                    space="DEV",
                    filename="123-test-page.md",
                )
            },
        )
        state.save(state_path)

        loaded = SyncState.load(state_path)
        assert loaded.last_sync == "2025-04-01T10:00:00Z"
        assert "123" in loaded.pages
        assert loaded.pages["123"].version == 5
        assert loaded.pages["123"].title == "Test Page"
        assert loaded.pages["123"].space == "DEV"
        assert loaded.pages["123"].filename == "123-test-page.md"

    def test_save_creates_parent_dirs(self, tmp_path):
        state_path = tmp_path / "sub" / "dir" / ".sync-state.json"
        state = SyncState(last_sync="2025-01-01T00:00:00Z")
        state.save(state_path)
        assert state_path.exists()

    def test_save_format(self, tmp_path):
        state_path = tmp_path / ".sync-state.json"
        state = SyncState(
            last_sync="2025-04-01T10:00:00Z",
            pages={
                "42": PageState(
                    version=1, title="Hello", space="OPS", filename="42-hello.md"
                )
            },
        )
        state.save(state_path)
        data = json.loads(state_path.read_text())
        assert data["last_sync"] == "2025-04-01T10:00:00Z"
        assert data["pages"]["42"]["version"] == 1
