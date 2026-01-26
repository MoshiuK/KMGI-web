"""
Roku Direct Publisher feed generator.
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from .models import Video, RokuVideo, RokuFeed, VideoType
from .config import RokuConfig
from .exceptions import RokuFeedError, RokuValidationError

logger = logging.getLogger(__name__)


class RokuFeedGenerator:
    """
    Generates Roku Direct Publisher JSON feeds from video content.

    Supports creating feeds with movies, short-form videos, series,
    and playlists according to Roku's feed specification.
    """

    # Roku feed validation rules
    TITLE_MAX_LENGTH = 100
    SHORT_DESC_MAX_LENGTH = 200
    LONG_DESC_MAX_LENGTH = 500
    MIN_THUMBNAIL_WIDTH = 800
    MIN_THUMBNAIL_HEIGHT = 450

    def __init__(self, config: RokuConfig = None, provider_name: str = None):
        """
        Initialize the Roku feed generator.

        Args:
            config: RokuConfig object
            provider_name: Provider name (alternative to config)
        """
        self.config = config or RokuConfig()
        self.provider_name = provider_name or self.config.provider_name

        if not self.provider_name:
            raise RokuFeedError("Provider name is required")

        self.feed = RokuFeed(
            provider_name=self.provider_name,
            language=self.config.language
        )

    def reset(self):
        """Reset the feed to empty state."""
        self.feed = RokuFeed(
            provider_name=self.provider_name,
            language=self.config.language
        )

    def add_video(
        self,
        video: Video,
        video_type: VideoType = None,
        genres: List[str] = None,
        rating: Dict[str, str] = None
    ) -> RokuVideo:
        """
        Add a video to the feed.

        Args:
            video: Video object from Vimeo
            video_type: Override video type classification
            genres: Override genres
            rating: Content rating (e.g., {"rating": "TV-G", "ratingSource": "USA_TV"})

        Returns:
            RokuVideo object that was added
        """
        # Determine video type if not specified
        if video_type is None:
            if video.duration < self.config.short_form_max_duration if hasattr(self.config, 'short_form_max_duration') else 900:
                video_type = VideoType.SHORT_FORM
            else:
                video_type = VideoType.MOVIE

        # Convert to Roku format
        roku_video = RokuVideo.from_video(video, video_type)

        # Apply overrides
        if genres:
            roku_video.genres = genres
        elif not roku_video.genres:
            roku_video.genres = [self.config.default_genre]

        if rating:
            roku_video.rating = rating
        elif self.config.rating_system and self.config.default_rating:
            roku_video.rating = {
                "rating": self.config.default_rating,
                "ratingSource": self.config.rating_system
            }

        # Add to feed
        self.feed.add_video(roku_video)

        logger.debug(f"Added video '{roku_video.title}' as {video_type.value}")
        return roku_video

    def add_videos(
        self,
        videos: List[Video],
        video_type: VideoType = None,
        genres: List[str] = None
    ) -> List[RokuVideo]:
        """
        Add multiple videos to the feed.

        Args:
            videos: List of Video objects
            video_type: Override video type for all videos
            genres: Override genres for all videos

        Returns:
            List of RokuVideo objects that were added
        """
        roku_videos = []
        for video in videos:
            roku_video = self.add_video(video, video_type, genres)
            roku_videos.append(roku_video)
        return roku_videos

    def add_series(
        self,
        series_id: str,
        title: str,
        episodes: List[Video],
        seasons: Dict[int, List[int]] = None,
        description: str = "",
        thumbnail: str = "",
        genres: List[str] = None,
        release_date: str = None
    ):
        """
        Add a series with episodes to the feed.

        Args:
            series_id: Unique series identifier
            title: Series title
            episodes: List of episode videos
            seasons: Dict mapping season number to episode indices
            description: Series description
            thumbnail: Series thumbnail URL
            genres: Series genres
            release_date: Series release date
        """
        # If no seasons provided, put all episodes in season 1
        if seasons is None:
            seasons = {1: list(range(len(episodes)))}

        # Build seasons array
        seasons_data = []
        for season_num in sorted(seasons.keys()):
            episode_indices = seasons[season_num]
            episodes_data = []

            for ep_idx, video_idx in enumerate(episode_indices):
                if video_idx >= len(episodes):
                    continue

                video = episodes[video_idx]
                thumbnail_obj = video.get_best_thumbnail()
                video_file = video.get_best_video_file()

                episode_data = {
                    "id": f"{series_id}-s{season_num}e{ep_idx + 1}",
                    "title": video.title,
                    "episodeNumber": ep_idx + 1,
                    "shortDescription": video.description[:200] if video.description else video.title,
                    "longDescription": video.description[:500] if video.description else video.title,
                    "releaseDate": video.release_date.strftime("%Y-%m-%d") if video.release_date else "",
                    "thumbnail": thumbnail_obj.url if thumbnail_obj else "",
                    "content": {
                        "dateAdded": video.created_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "duration": video.duration,
                        "videos": []
                    }
                }

                if video_file:
                    episode_data["content"]["videos"].append({
                        "url": video_file.url,
                        "quality": video_file.quality.value,
                        "videoType": video_file.video_type
                    })

                episodes_data.append(episode_data)

            seasons_data.append({
                "seasonNumber": season_num,
                "episodes": episodes_data
            })

        # Get series thumbnail from first episode if not provided
        if not thumbnail and episodes:
            first_thumb = episodes[0].get_best_thumbnail()
            thumbnail = first_thumb.url if first_thumb else ""

        series_data = {
            "id": series_id,
            "title": title[:100],
            "shortDescription": description[:200] if description else title,
            "longDescription": description[:500] if description else title,
            "thumbnail": thumbnail,
            "releaseDate": release_date or (episodes[0].release_date.strftime("%Y-%m-%d") if episodes else ""),
            "genres": genres or [self.config.default_genre],
            "seasons": seasons_data
        }

        self.feed.series.append(series_data)
        logger.debug(f"Added series '{title}' with {len(episodes)} episodes")

    def add_playlist(
        self,
        playlist_id: str,
        name: str,
        video_ids: List[str]
    ):
        """
        Add a playlist/category to the feed.

        Args:
            playlist_id: Unique playlist identifier
            name: Playlist name
            video_ids: List of video IDs in the playlist
        """
        playlist_data = {
            "name": name,
            "playlistId": playlist_id,
            "itemIds": video_ids
        }
        self.feed.playlists.append(playlist_data)
        logger.debug(f"Added playlist '{name}' with {len(video_ids)} items")

    def add_category(
        self,
        name: str,
        playlist_ids: List[str],
        order: str = "manual"
    ):
        """
        Add a category that groups playlists.

        Args:
            name: Category name
            playlist_ids: List of playlist IDs in this category
            order: Ordering method (manual, most_recent, etc.)
        """
        category_data = {
            "name": name,
            "playlistIds": playlist_ids,
            "order": order
        }
        self.feed.categories.append(category_data)

    def validate(self) -> List[str]:
        """
        Validate the feed against Roku requirements.

        Returns:
            List of validation error messages
        """
        errors = []

        if not self.feed.provider_name:
            errors.append("Provider name is required")

        # Validate short form videos
        for video in self.feed.short_form_videos:
            errors.extend(self._validate_video(video, "shortFormVideo"))

        # Validate movies
        for video in self.feed.movies:
            errors.extend(self._validate_video(video, "movie"))

        # Validate series
        for series in self.feed.series:
            if not series.get("id"):
                errors.append("Series missing required 'id' field")
            if not series.get("title"):
                errors.append("Series missing required 'title' field")
            if not series.get("seasons"):
                errors.append(f"Series '{series.get('id')}' has no seasons")

        return errors

    def _validate_video(self, video: RokuVideo, video_type: str) -> List[str]:
        """Validate a single video."""
        errors = []
        prefix = f"{video_type} '{video.id}'"

        if not video.id:
            errors.append(f"{prefix}: Missing required 'id' field")

        if not video.title:
            errors.append(f"{prefix}: Missing required 'title' field")
        elif len(video.title) > self.TITLE_MAX_LENGTH:
            errors.append(f"{prefix}: Title exceeds {self.TITLE_MAX_LENGTH} characters")

        if len(video.short_description) > self.SHORT_DESC_MAX_LENGTH:
            errors.append(f"{prefix}: Short description exceeds {self.SHORT_DESC_MAX_LENGTH} characters")

        if not video.thumbnail:
            errors.append(f"{prefix}: Missing required 'thumbnail' field")

        if not video.content.get("videos"):
            errors.append(f"{prefix}: No video content URLs provided")

        return errors

    def is_valid(self) -> bool:
        """Check if the feed is valid."""
        return len(self.validate()) == 0

    def update_timestamp(self):
        """Update the lastUpdated timestamp to now."""
        self.feed.last_updated = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Get the feed as a dictionary."""
        self.update_timestamp()
        return self.feed.to_dict()

    def to_json(self, indent: int = 2) -> str:
        """Get the feed as a JSON string."""
        self.update_timestamp()
        return self.feed.to_json(indent)

    def save(self, filepath: str = None):
        """
        Save the feed to a JSON file.

        Args:
            filepath: Output file path (uses config path if not specified)
        """
        filepath = filepath or self.config.feed_output_path

        # Validate before saving
        errors = self.validate()
        if errors:
            logger.warning(f"Feed has {len(errors)} validation issues:")
            for error in errors[:10]:  # Log first 10 errors
                logger.warning(f"  - {error}")

        self.update_timestamp()

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        self.feed.save(str(path))
        logger.info(f"Feed saved to {filepath}")

        return filepath

    def get_stats(self) -> Dict[str, int]:
        """Get statistics about the feed content."""
        return {
            "short_form_videos": len(self.feed.short_form_videos),
            "movies": len(self.feed.movies),
            "series": len(self.feed.series),
            "tv_specials": len(self.feed.tv_specials),
            "playlists": len(self.feed.playlists),
            "categories": len(self.feed.categories),
            "total_videos": (
                len(self.feed.short_form_videos) +
                len(self.feed.movies) +
                len(self.feed.tv_specials)
            )
        }


class RokuFeedUploader:
    """
    Handles uploading Roku feeds to various destinations.
    """

    def __init__(self, config: RokuConfig = None):
        self.config = config or RokuConfig()

    def upload_to_s3(self, feed_path: str, bucket: str = None, key: str = None) -> str:
        """
        Upload feed to Amazon S3.

        Args:
            feed_path: Path to the feed JSON file
            bucket: S3 bucket name
            key: S3 object key

        Returns:
            S3 URL of the uploaded feed
        """
        try:
            import boto3
        except ImportError:
            raise RokuFeedError("boto3 is required for S3 upload. Install with: pip install boto3")

        bucket = bucket or self.config.s3_bucket
        key = key or self.config.s3_key or "roku-feed.json"

        if not bucket:
            raise RokuFeedError("S3 bucket is required")

        s3 = boto3.client("s3")

        with open(feed_path, "rb") as f:
            s3.upload_fileobj(
                f,
                bucket,
                key,
                ExtraArgs={
                    "ContentType": "application/json",
                    "ACL": "public-read"
                }
            )

        url = f"https://{bucket}.s3.amazonaws.com/{key}"
        logger.info(f"Feed uploaded to S3: {url}")
        return url

    def notify_webhook(self, feed_url: str, webhook_url: str = None) -> bool:
        """
        Send a webhook notification that the feed has been updated.

        Args:
            feed_url: URL of the updated feed
            webhook_url: Webhook URL to notify

        Returns:
            True if notification was successful
        """
        import requests

        webhook_url = webhook_url or self.config.webhook_url
        if not webhook_url:
            return False

        try:
            response = requests.post(
                webhook_url,
                json={
                    "event": "feed_updated",
                    "feed_url": feed_url,
                    "timestamp": datetime.now().isoformat()
                },
                timeout=30
            )
            response.raise_for_status()
            logger.info(f"Webhook notification sent to {webhook_url}")
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to send webhook notification: {e}")
            return False
