"""
Configuration handling for the Vimeo to Roku SDK.
"""

import os
import yaml
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from pathlib import Path

from .exceptions import ConfigurationError


@dataclass
class VimeoConfig:
    """Vimeo API configuration."""
    client_id: str = ""
    client_secret: str = ""
    access_token: str = ""
    user_id: Optional[str] = None  # If not set, uses authenticated user
    folder_id: Optional[str] = None  # Specific folder to sync
    album_id: Optional[str] = None  # Specific album/showcase to sync

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VimeoConfig":
        return cls(
            client_id=data.get("client_id", ""),
            client_secret=data.get("client_secret", ""),
            access_token=data.get("access_token", ""),
            user_id=data.get("user_id"),
            folder_id=data.get("folder_id"),
            album_id=data.get("album_id")
        )

    @classmethod
    def from_env(cls) -> "VimeoConfig":
        """Load configuration from environment variables."""
        return cls(
            client_id=os.getenv("VIMEO_CLIENT_ID", ""),
            client_secret=os.getenv("VIMEO_CLIENT_SECRET", ""),
            access_token=os.getenv("VIMEO_ACCESS_TOKEN", ""),
            user_id=os.getenv("VIMEO_USER_ID"),
            folder_id=os.getenv("VIMEO_FOLDER_ID"),
            album_id=os.getenv("VIMEO_ALBUM_ID")
        )


@dataclass
class RokuConfig:
    """Roku channel configuration."""
    provider_name: str = ""
    channel_id: Optional[str] = None
    language: str = "en"
    feed_output_path: str = "./roku_feed.json"
    default_genre: str = "Entertainment"
    rating_system: str = "USA_TV"
    default_rating: str = "TV-G"

    # Feed hosting options
    s3_bucket: Optional[str] = None
    s3_key: Optional[str] = None
    webhook_url: Optional[str] = None  # Webhook to notify when feed is updated

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RokuConfig":
        return cls(
            provider_name=data.get("provider_name", ""),
            channel_id=data.get("channel_id"),
            language=data.get("language", "en"),
            feed_output_path=data.get("feed_output_path", "./roku_feed.json"),
            default_genre=data.get("default_genre", "Entertainment"),
            rating_system=data.get("rating_system", "USA_TV"),
            default_rating=data.get("default_rating", "TV-G"),
            s3_bucket=data.get("s3_bucket"),
            s3_key=data.get("s3_key"),
            webhook_url=data.get("webhook_url")
        )

    @classmethod
    def from_env(cls) -> "RokuConfig":
        """Load configuration from environment variables."""
        return cls(
            provider_name=os.getenv("ROKU_PROVIDER_NAME", ""),
            channel_id=os.getenv("ROKU_CHANNEL_ID"),
            language=os.getenv("ROKU_LANGUAGE", "en"),
            feed_output_path=os.getenv("ROKU_FEED_OUTPUT_PATH", "./roku_feed.json"),
            default_genre=os.getenv("ROKU_DEFAULT_GENRE", "Entertainment"),
            rating_system=os.getenv("ROKU_RATING_SYSTEM", "USA_TV"),
            default_rating=os.getenv("ROKU_DEFAULT_RATING", "TV-G"),
            s3_bucket=os.getenv("ROKU_S3_BUCKET"),
            s3_key=os.getenv("ROKU_S3_KEY"),
            webhook_url=os.getenv("ROKU_WEBHOOK_URL")
        )


@dataclass
class SyncConfig:
    """Sync configuration."""
    # Filter options
    include_private: bool = False
    min_duration: int = 0  # Minimum duration in seconds
    max_duration: Optional[int] = None  # Maximum duration in seconds
    include_tags: List[str] = field(default_factory=list)  # Only include videos with these tags
    exclude_tags: List[str] = field(default_factory=list)  # Exclude videos with these tags

    # Video type mapping
    short_form_max_duration: int = 900  # 15 minutes - videos shorter are short form

    # Caching
    cache_enabled: bool = True
    cache_path: str = "./.vimeo_roku_cache"

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SyncConfig":
        return cls(
            include_private=data.get("include_private", False),
            min_duration=data.get("min_duration", 0),
            max_duration=data.get("max_duration"),
            include_tags=data.get("include_tags", []),
            exclude_tags=data.get("exclude_tags", []),
            short_form_max_duration=data.get("short_form_max_duration", 900),
            cache_enabled=data.get("cache_enabled", True),
            cache_path=data.get("cache_path", "./.vimeo_roku_cache"),
            log_level=data.get("log_level", "INFO"),
            log_file=data.get("log_file")
        )

    @classmethod
    def from_env(cls) -> "SyncConfig":
        """Load configuration from environment variables."""
        include_tags = os.getenv("SYNC_INCLUDE_TAGS", "")
        exclude_tags = os.getenv("SYNC_EXCLUDE_TAGS", "")

        return cls(
            include_private=os.getenv("SYNC_INCLUDE_PRIVATE", "false").lower() == "true",
            min_duration=int(os.getenv("SYNC_MIN_DURATION", "0")),
            max_duration=int(os.getenv("SYNC_MAX_DURATION")) if os.getenv("SYNC_MAX_DURATION") else None,
            include_tags=[t.strip() for t in include_tags.split(",") if t.strip()],
            exclude_tags=[t.strip() for t in exclude_tags.split(",") if t.strip()],
            short_form_max_duration=int(os.getenv("SYNC_SHORT_FORM_MAX_DURATION", "900")),
            cache_enabled=os.getenv("SYNC_CACHE_ENABLED", "true").lower() == "true",
            cache_path=os.getenv("SYNC_CACHE_PATH", "./.vimeo_roku_cache"),
            log_level=os.getenv("SYNC_LOG_LEVEL", "INFO"),
            log_file=os.getenv("SYNC_LOG_FILE")
        )


@dataclass
class Config:
    """Main configuration class."""
    vimeo: VimeoConfig = field(default_factory=VimeoConfig)
    roku: RokuConfig = field(default_factory=RokuConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)

    @classmethod
    def from_yaml(cls, filepath: str) -> "Config":
        """Load configuration from a YAML file."""
        path = Path(filepath)
        if not path.exists():
            raise ConfigurationError(f"Configuration file not found: {filepath}")

        try:
            with open(path, "r") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML in configuration file: {e}")

        return cls(
            vimeo=VimeoConfig.from_dict(data.get("vimeo", {})),
            roku=RokuConfig.from_dict(data.get("roku", {})),
            sync=SyncConfig.from_dict(data.get("sync", {}))
        )

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls(
            vimeo=VimeoConfig.from_env(),
            roku=RokuConfig.from_env(),
            sync=SyncConfig.from_env()
        )

    @classmethod
    def from_yaml_with_env(cls, filepath: str) -> "Config":
        """Load configuration from YAML file, with environment variable overrides."""
        config = cls.from_yaml(filepath)
        env_config = cls.from_env()

        # Override with environment variables if they're set
        if os.getenv("VIMEO_ACCESS_TOKEN"):
            config.vimeo.access_token = env_config.vimeo.access_token
        if os.getenv("VIMEO_CLIENT_ID"):
            config.vimeo.client_id = env_config.vimeo.client_id
        if os.getenv("VIMEO_CLIENT_SECRET"):
            config.vimeo.client_secret = env_config.vimeo.client_secret

        return config

    def validate(self) -> List[str]:
        """Validate the configuration and return a list of errors."""
        errors = []

        if not self.vimeo.access_token:
            errors.append("Vimeo access token is required")

        if not self.roku.provider_name:
            errors.append("Roku provider name is required")

        return errors

    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return len(self.validate()) == 0
