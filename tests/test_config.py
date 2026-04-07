import os
from pathlib import Path

import pytest

from confluence_sync.config import Config, SyncConfig


class TestConfig:
    def test_load(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CONFLUENCE_BASE_URL", raising=False)
        config_path = tmp_path / ".confluence-sync.toml"
        config_path.write_text(
            'base_url = "https://confluence.example.com/"\n'
            'output_dir = "./out"\n'
            'spaces = ["DEV", "OPS"]\n'
            "\n"
            "[sync]\n"
            "include_attachments = false\n"
            'attachment_dir = "_files"\n'
        )
        config = Config.load(config_path)
        # trailing slash should be stripped
        assert config.base_url == "https://confluence.example.com"
        assert config.output_dir == "./out"
        assert config.spaces == ["DEV", "OPS"]
        assert config.sync.include_attachments is False
        assert config.sync.attachment_dir == "_files"

    def test_load_defaults(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CONFLUENCE_BASE_URL", raising=False)
        config_path = tmp_path / ".confluence-sync.toml"
        config_path.write_text('base_url = "https://x.com"\n')
        config = Config.load(config_path)
        assert config.output_dir == "./confluence-export"
        assert config.spaces == []
        assert config.sync.include_attachments is True
        assert config.sync.attachment_dir == "_attachments"

    def test_load_base_url_from_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CONFLUENCE_BASE_URL", "https://from-env.example.com/")
        config_path = tmp_path / ".confluence-sync.toml"
        config_path.write_text('base_url = "https://from-file.example.com"\n')
        config = Config.load(config_path)
        assert config.base_url == "https://from-env.example.com"

    def test_load_base_url_fallback_to_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CONFLUENCE_BASE_URL", raising=False)
        config_path = tmp_path / ".confluence-sync.toml"
        config_path.write_text('base_url = "https://from-file.example.com"\n')
        config = Config.load(config_path)
        assert config.base_url == "https://from-file.example.com"

    def test_get_pat_success(self, monkeypatch):
        monkeypatch.setenv("CONFLUENCE_PAT", "test-token-123")
        config = Config(base_url="https://x.com")
        assert config.get_pat() == "test-token-123"

    def test_get_pat_missing(self, monkeypatch):
        monkeypatch.delenv("CONFLUENCE_PAT", raising=False)
        config = Config(base_url="https://x.com")
        with pytest.raises(SystemExit):
            config.get_pat()
