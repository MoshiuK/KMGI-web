"""
Tests for configuration handling.
"""

import os
import pytest
import tempfile
from pathlib import Path

from vimeo_roku_sdk.config import (
    Config,
    VimeoConfig,
    RokuConfig,
    SyncConfig
)
from vimeo_roku_sdk.exceptions import ConfigurationError


class TestVimeoConfig:
    """Tests for VimeoConfig."""

    def test_from_dict(self):
        """Test creating VimeoConfig from dictionary."""
        data = {
            "access_token": "test_token",
            "client_id": "client_123",
            "user_id": "user_456"
        }

        config = VimeoConfig.from_dict(data)

        assert config.access_token == "test_token"
        assert config.client_id == "client_123"
        assert config.user_id == "user_456"

    def test_from_env(self, monkeypatch):
        """Test creating VimeoConfig from environment."""
        monkeypatch.setenv("VIMEO_ACCESS_TOKEN", "env_token")
        monkeypatch.setenv("VIMEO_CLIENT_ID", "env_client")

        config = VimeoConfig.from_env()

        assert config.access_token == "env_token"
        assert config.client_id == "env_client"


class TestRokuConfig:
    """Tests for RokuConfig."""

    def test_from_dict(self):
        """Test creating RokuConfig from dictionary."""
        data = {
            "provider_name": "My Channel",
            "language": "es",
            "feed_output_path": "/custom/path.json"
        }

        config = RokuConfig.from_dict(data)

        assert config.provider_name == "My Channel"
        assert config.language == "es"
        assert config.feed_output_path == "/custom/path.json"

    def test_defaults(self):
        """Test default values."""
        config = RokuConfig()

        assert config.language == "en"
        assert config.default_genre == "Entertainment"
        assert config.default_rating == "TV-G"


class TestSyncConfig:
    """Tests for SyncConfig."""

    def test_from_dict(self):
        """Test creating SyncConfig from dictionary."""
        data = {
            "include_private": True,
            "min_duration": 60,
            "include_tags": ["featured", "public"],
            "exclude_tags": ["draft"]
        }

        config = SyncConfig.from_dict(data)

        assert config.include_private is True
        assert config.min_duration == 60
        assert "featured" in config.include_tags
        assert "draft" in config.exclude_tags

    def test_from_env(self, monkeypatch):
        """Test creating SyncConfig from environment."""
        monkeypatch.setenv("SYNC_INCLUDE_PRIVATE", "true")
        monkeypatch.setenv("SYNC_MIN_DURATION", "120")
        monkeypatch.setenv("SYNC_INCLUDE_TAGS", "tag1, tag2, tag3")

        config = SyncConfig.from_env()

        assert config.include_private is True
        assert config.min_duration == 120
        assert "tag1" in config.include_tags
        assert "tag2" in config.include_tags


class TestConfig:
    """Tests for main Config class."""

    def test_from_yaml(self):
        """Test loading config from YAML file."""
        yaml_content = """
vimeo:
  access_token: "yaml_token"

roku:
  provider_name: "YAML Channel"
  language: "fr"

sync:
  min_duration: 30
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                config = Config.from_yaml(f.name)

                assert config.vimeo.access_token == "yaml_token"
                assert config.roku.provider_name == "YAML Channel"
                assert config.roku.language == "fr"
                assert config.sync.min_duration == 30
            finally:
                os.unlink(f.name)

    def test_from_yaml_not_found(self):
        """Test error when YAML file not found."""
        with pytest.raises(ConfigurationError):
            Config.from_yaml("/nonexistent/path.yaml")

    def test_validate_missing_token(self):
        """Test validation catches missing access token."""
        config = Config(
            vimeo=VimeoConfig(access_token=""),
            roku=RokuConfig(provider_name="Test")
        )

        errors = config.validate()
        assert any("access token" in e.lower() for e in errors)

    def test_validate_missing_provider(self):
        """Test validation catches missing provider name."""
        config = Config(
            vimeo=VimeoConfig(access_token="token"),
            roku=RokuConfig(provider_name="")
        )

        errors = config.validate()
        assert any("provider name" in e.lower() for e in errors)

    def test_is_valid(self):
        """Test is_valid method."""
        valid_config = Config(
            vimeo=VimeoConfig(access_token="token"),
            roku=RokuConfig(provider_name="Provider")
        )

        invalid_config = Config(
            vimeo=VimeoConfig(access_token=""),
            roku=RokuConfig(provider_name="")
        )

        assert valid_config.is_valid() is True
        assert invalid_config.is_valid() is False
