"""
Sync manager for orchestrating Vimeo to Roku content synchronization.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field

from .vimeo_client import VimeoClient
from .roku_feed import RokuFeedGenerator, RokuFeedUploader
from .models import Video, RokuVideo, VideoType
from .config import Config, VimeoConfig, RokuConfig, SyncConfig
from .exceptions import SyncError, VimeoAPIError, RokuFeedError

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success: bool
    videos_processed: int = 0
    videos_added: int = 0
    videos_skipped: int = 0
    videos_failed: int = 0
    feed_path: Optional[str] = None
    feed_url: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "videos_processed": self.videos_processed,
            "videos_added": self.videos_added,
            "videos_skipped": self.videos_skipped,
            "videos_failed": self.videos_failed,
            "feed_path": self.feed_path,
            "feed_url": self.feed_url,
            "errors": self.errors,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class SyncState:
    """Persistent state for incremental syncs."""
    last_sync: Optional[datetime] = None
    last_video_count: int = 0
    synced_video_ids: List[str] = field(default_factory=list)

    @classmethod
    def load(cls, filepath: str) -> "SyncState":
        """Load state from a JSON file."""
        path = Path(filepath)
        if not path.exists():
            return cls()

        try:
            with open(path, "r") as f:
                data = json.load(f)
            return cls(
                last_sync=datetime.fromisoformat(data["last_sync"]) if data.get("last_sync") else None,
                last_video_count=data.get("last_video_count", 0),
                synced_video_ids=data.get("synced_video_ids", [])
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to load sync state: {e}")
            return cls()

    def save(self, filepath: str):
        """Save state to a JSON file."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "last_video_count": self.last_video_count,
            "synced_video_ids": self.synced_video_ids
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)


class SyncManager:
    """
    Manages the synchronization of videos from Vimeo to Roku.

    Handles:
    - Fetching videos from Vimeo (all, album, folder)
    - Filtering videos based on configuration
    - Converting to Roku format
    - Generating and saving the feed
    - Uploading to S3 (optional)
    - Webhook notifications (optional)
    - Incremental syncs with state persistence
    """

    def __init__(
        self,
        config: Config = None,
        vimeo_client: VimeoClient = None,
        feed_generator: RokuFeedGenerator = None
    ):
        """
        Initialize the sync manager.

        Args:
            config: Configuration object
            vimeo_client: Pre-configured Vimeo client (optional)
            feed_generator: Pre-configured feed generator (optional)
        """
        self.config = config or Config()

        # Initialize clients
        self.vimeo = vimeo_client or VimeoClient(config=self.config.vimeo)
        self.feed_generator = feed_generator or RokuFeedGenerator(config=self.config.roku)
        self.uploader = RokuFeedUploader(config=self.config.roku)

        # State for incremental syncs
        self._state_path = Path(self.config.sync.cache_path) / "sync_state.json"
        self._state: Optional[SyncState] = None

        # Callbacks
        self._on_video_processed: Optional[Callable[[Video, bool], None]] = None
        self._on_progress: Optional[Callable[[int, int], None]] = None

    def set_callbacks(
        self,
        on_video_processed: Callable[[Video, bool], None] = None,
        on_progress: Callable[[int, int], None] = None
    ):
        """
        Set callback functions for sync events.

        Args:
            on_video_processed: Called when a video is processed (video, was_added)
            on_progress: Called with progress updates (current, total)
        """
        self._on_video_processed = on_video_processed
        self._on_progress = on_progress

    def _load_state(self) -> SyncState:
        """Load sync state from disk."""
        if self._state is None:
            if self.config.sync.cache_enabled:
                self._state = SyncState.load(str(self._state_path))
            else:
                self._state = SyncState()
        return self._state

    def _save_state(self):
        """Save sync state to disk."""
        if self._state and self.config.sync.cache_enabled:
            self._state.save(str(self._state_path))

    def _should_include_video(self, video: Video) -> bool:
        """
        Check if a video should be included based on filter criteria.

        Args:
            video: Video to check

        Returns:
            True if video should be included
        """
        # Check privacy
        if not self.config.sync.include_private and video.privacy != "anybody":
            logger.debug(f"Skipping private video: {video.title}")
            return False

        # Check duration
        if video.duration < self.config.sync.min_duration:
            logger.debug(f"Skipping short video: {video.title} ({video.duration}s)")
            return False

        if self.config.sync.max_duration and video.duration > self.config.sync.max_duration:
            logger.debug(f"Skipping long video: {video.title} ({video.duration}s)")
            return False

        # Check include tags
        if self.config.sync.include_tags:
            video_tags = [t.lower() for t in video.tags]
            include_tags = [t.lower() for t in self.config.sync.include_tags]
            if not any(tag in video_tags for tag in include_tags):
                logger.debug(f"Skipping video without required tags: {video.title}")
                return False

        # Check exclude tags
        if self.config.sync.exclude_tags:
            video_tags = [t.lower() for t in video.tags]
            exclude_tags = [t.lower() for t in self.config.sync.exclude_tags]
            if any(tag in video_tags for tag in exclude_tags):
                logger.debug(f"Skipping video with excluded tag: {video.title}")
                return False

        # Check for playable content
        if not video.get_best_video_file():
            logger.warning(f"Skipping video without playable content: {video.title}")
            return False

        return True

    def _determine_video_type(self, video: Video) -> VideoType:
        """Determine the Roku video type based on duration."""
        if video.duration < self.config.sync.short_form_max_duration:
            return VideoType.SHORT_FORM
        return VideoType.MOVIE

    def fetch_videos(
        self,
        source: str = "all",
        album_id: str = None,
        folder_id: str = None,
        limit: int = None
    ) -> List[Video]:
        """
        Fetch videos from Vimeo.

        Args:
            source: Video source ('all', 'album', 'folder')
            album_id: Album ID if source is 'album'
            folder_id: Folder ID if source is 'folder'
            limit: Maximum number of videos to fetch

        Returns:
            List of Video objects
        """
        logger.info(f"Fetching videos from Vimeo (source: {source})...")

        videos = []

        if source == "album":
            album_id = album_id or self.config.vimeo.album_id
            for video in self.vimeo.iter_album_videos(album_id=album_id):
                videos.append(video)
                if limit and len(videos) >= limit:
                    break

        elif source == "folder":
            folder_id = folder_id or self.config.vimeo.folder_id
            for video in self.vimeo.iter_folder_videos(folder_id=folder_id):
                videos.append(video)
                if limit and len(videos) >= limit:
                    break

        else:  # all
            videos = self.vimeo.get_all_videos(limit=limit)

        logger.info(f"Fetched {len(videos)} videos from Vimeo")
        return videos

    def sync(
        self,
        source: str = "all",
        album_id: str = None,
        folder_id: str = None,
        incremental: bool = False,
        upload: bool = False,
        notify: bool = False
    ) -> SyncResult:
        """
        Perform a full sync from Vimeo to Roku.

        Args:
            source: Video source ('all', 'album', 'folder')
            album_id: Album ID if source is 'album'
            folder_id: Folder ID if source is 'folder'
            incremental: Only sync videos modified since last sync
            upload: Upload feed to S3 after generating
            notify: Send webhook notification after sync

        Returns:
            SyncResult with details of the operation
        """
        start_time = datetime.now()
        result = SyncResult(success=False)

        try:
            # Load state for incremental sync
            state = self._load_state()

            # Reset feed generator
            self.feed_generator.reset()

            # Fetch videos
            if incremental and state.last_sync:
                logger.info(f"Performing incremental sync since {state.last_sync}")
                videos = self.vimeo.get_videos_modified_since(state.last_sync)
            else:
                videos = self.fetch_videos(source, album_id, folder_id)

            total_videos = len(videos)
            logger.info(f"Processing {total_videos} videos...")

            # Process each video
            for idx, video in enumerate(videos):
                result.videos_processed += 1

                if self._on_progress:
                    self._on_progress(idx + 1, total_videos)

                try:
                    # Check if video should be included
                    if not self._should_include_video(video):
                        result.videos_skipped += 1
                        if self._on_video_processed:
                            self._on_video_processed(video, False)
                        continue

                    # Determine video type and add to feed
                    video_type = self._determine_video_type(video)
                    self.feed_generator.add_video(video, video_type)

                    result.videos_added += 1
                    state.synced_video_ids.append(video.id)

                    if self._on_video_processed:
                        self._on_video_processed(video, True)

                except Exception as e:
                    logger.error(f"Failed to process video {video.id}: {e}")
                    result.videos_failed += 1
                    result.errors.append(f"Video {video.id}: {str(e)}")

            # Validate and save feed
            validation_errors = self.feed_generator.validate()
            if validation_errors:
                for error in validation_errors:
                    result.errors.append(f"Validation: {error}")

            feed_path = self.feed_generator.save()
            result.feed_path = feed_path

            # Upload to S3 if requested
            if upload and self.config.roku.s3_bucket:
                try:
                    result.feed_url = self.uploader.upload_to_s3(feed_path)
                except Exception as e:
                    logger.error(f"Failed to upload to S3: {e}")
                    result.errors.append(f"S3 upload: {str(e)}")

            # Send webhook notification if requested
            if notify and result.feed_url:
                self.uploader.notify_webhook(result.feed_url)

            # Update state
            state.last_sync = datetime.now()
            state.last_video_count = result.videos_added
            self._save_state()

            result.success = True
            logger.info(
                f"Sync completed: {result.videos_added} added, "
                f"{result.videos_skipped} skipped, {result.videos_failed} failed"
            )

        except VimeoAPIError as e:
            logger.error(f"Vimeo API error during sync: {e}")
            result.errors.append(f"Vimeo API: {str(e)}")

        except RokuFeedError as e:
            logger.error(f"Roku feed error during sync: {e}")
            result.errors.append(f"Roku feed: {str(e)}")

        except Exception as e:
            logger.error(f"Unexpected error during sync: {e}")
            result.errors.append(f"Unexpected: {str(e)}")

        finally:
            result.duration_seconds = (datetime.now() - start_time).total_seconds()

        return result

    def sync_album(self, album_id: str = None, **kwargs) -> SyncResult:
        """
        Sync videos from a specific album/showcase.

        Args:
            album_id: Vimeo album ID
            **kwargs: Additional arguments passed to sync()

        Returns:
            SyncResult
        """
        return self.sync(source="album", album_id=album_id, **kwargs)

    def sync_folder(self, folder_id: str = None, **kwargs) -> SyncResult:
        """
        Sync videos from a specific folder/project.

        Args:
            folder_id: Vimeo folder ID
            **kwargs: Additional arguments passed to sync()

        Returns:
            SyncResult
        """
        return self.sync(source="folder", folder_id=folder_id, **kwargs)

    def get_feed_stats(self) -> Dict[str, Any]:
        """Get statistics about the current feed."""
        return self.feed_generator.get_stats()

    def get_last_sync_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the last sync."""
        state = self._load_state()
        if not state.last_sync:
            return None

        return {
            "last_sync": state.last_sync.isoformat(),
            "video_count": state.last_video_count,
            "synced_ids_count": len(state.synced_video_ids)
        }

    def clear_cache(self):
        """Clear the sync state cache."""
        self._state = SyncState()
        if self._state_path.exists():
            self._state_path.unlink()
        logger.info("Sync cache cleared")


def create_sync_manager(
    vimeo_access_token: str,
    roku_provider_name: str,
    feed_output_path: str = "./roku_feed.json",
    **kwargs
) -> SyncManager:
    """
    Convenience function to create a SyncManager with minimal configuration.

    Args:
        vimeo_access_token: Vimeo API access token
        roku_provider_name: Roku channel provider name
        feed_output_path: Path to save the feed JSON
        **kwargs: Additional configuration options

    Returns:
        Configured SyncManager instance
    """
    config = Config(
        vimeo=VimeoConfig(access_token=vimeo_access_token),
        roku=RokuConfig(
            provider_name=roku_provider_name,
            feed_output_path=feed_output_path
        ),
        sync=SyncConfig(**kwargs)
    )

    return SyncManager(config=config)
