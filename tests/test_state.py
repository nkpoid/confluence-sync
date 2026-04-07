from confluence_sync.state import DB_FILENAME, PageState, SyncState


class TestSyncState:
    def test_new_db(self, tmp_path):
        state = SyncState(tmp_path / DB_FILENAME)
        assert state.last_sync == ""
        assert state.page_count == 0
        state.close()

    def test_last_sync(self, tmp_path):
        state = SyncState(tmp_path / DB_FILENAME)
        state.last_sync = "2025-04-01T10:00:00Z"
        assert state.last_sync == "2025-04-01T10:00:00Z"
        state.close()

        # 再度開いても値が残る
        state2 = SyncState(tmp_path / DB_FILENAME)
        assert state2.last_sync == "2025-04-01T10:00:00Z"
        state2.close()

    def test_upsert_and_get_page(self, tmp_path):
        state = SyncState(tmp_path / DB_FILENAME)
        ps = PageState(version=5, title="Test Page", space="DEV", filename="123-test-page.md")
        state.upsert_page("123", ps)

        loaded = state.get_page("123")
        assert loaded is not None
        assert loaded.version == 5
        assert loaded.title == "Test Page"
        assert loaded.space == "DEV"
        assert loaded.filename == "123-test-page.md"
        state.close()

    def test_upsert_overwrites(self, tmp_path):
        state = SyncState(tmp_path / DB_FILENAME)
        state.upsert_page("1", PageState(version=1, title="V1", space="S", filename="1-v1.md"))
        state.upsert_page("1", PageState(version=2, title="V2", space="S", filename="1-v2.md"))

        loaded = state.get_page("1")
        assert loaded is not None
        assert loaded.version == 2
        assert loaded.title == "V2"
        state.close()

    def test_has_page(self, tmp_path):
        state = SyncState(tmp_path / DB_FILENAME)
        assert not state.has_page("99")
        state.upsert_page("99", PageState(version=1, title="T", space="S", filename="99-t.md"))
        assert state.has_page("99")
        state.close()

    def test_delete_page(self, tmp_path):
        state = SyncState(tmp_path / DB_FILENAME)
        state.upsert_page("1", PageState(version=1, title="T", space="S", filename="1-t.md"))
        assert state.has_page("1")
        state.delete_page("1")
        assert not state.has_page("1")
        state.close()

    def test_all_pages(self, tmp_path):
        state = SyncState(tmp_path / DB_FILENAME)
        state.upsert_page("1", PageState(version=1, title="A", space="S", filename="1-a.md"))
        state.upsert_page("2", PageState(version=2, title="B", space="S", filename="2-b.md"))

        all_pages = state.all_pages()
        assert len(all_pages) == 2
        assert "1" in all_pages
        assert "2" in all_pages
        state.close()

    def test_page_count(self, tmp_path):
        state = SyncState(tmp_path / DB_FILENAME)
        assert state.page_count == 0
        state.upsert_page("1", PageState(version=1, title="A", space="S", filename="1-a.md"))
        state.upsert_page("2", PageState(version=1, title="B", space="S", filename="2-b.md"))
        assert state.page_count == 2
        state.delete_page("1")
        assert state.page_count == 1
        state.close()

    def test_creates_parent_dirs(self, tmp_path):
        db_path = tmp_path / "sub" / "dir" / DB_FILENAME
        state = SyncState(db_path)
        state.last_sync = "2025-01-01T00:00:00Z"
        assert db_path.exists()
        state.close()
