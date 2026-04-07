from pathlib import Path

import pytest

from confluence_sync.config import Config, SyncConfig


class TestConfig:
    def test_load(self, tmp_path):
        config_path = tmp_path / ".confluence-sync.toml"
        config_path.write_text(
            'base_url = "https://confluence.example.com/"\n'
            'pat = "test-token"\n'
            'output_dir = "./out"\n'
            'spaces = ["DEV", "OPS"]\n'
            "\n"
            "[sync]\n"
            "include_attachments = false\n"
            'attachment_dir = "_files"\n'
        )
        config = Config.load(config_path)
        assert config.base_url == "https://confluence.example.com"
        assert config.pat == "test-token"
        assert config.output_dir == "./out"
        assert config.spaces == ["DEV", "OPS"]
        assert config.sync.include_attachments is False
        assert config.sync.attachment_dir == "_files"

    def test_load_defaults(self, tmp_path):
        config_path = tmp_path / ".confluence-sync.toml"
        config_path.write_text(
            'base_url = "https://x.com"\n'
            'pat = "token"\n'
        )
        config = Config.load(config_path)
        assert config.output_dir == "./confluence-export"
        assert config.spaces == []
        assert config.sync.include_attachments is True
        assert config.sync.attachment_dir == "_attachments"

    def test_load_missing_base_url(self, tmp_path):
        config_path = tmp_path / ".confluence-sync.toml"
        config_path.write_text('pat = "token"\n')
        with pytest.raises(SystemExit):
            Config.load(config_path)

    def test_load_missing_pat(self, tmp_path):
        config_path = tmp_path / ".confluence-sync.toml"
        config_path.write_text('base_url = "https://x.com"\n')
        with pytest.raises(SystemExit):
            Config.load(config_path)
