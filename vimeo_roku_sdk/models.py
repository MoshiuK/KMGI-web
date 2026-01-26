"""
Data models for Vimeo and Roku video content.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
import json


class VideoType(Enum):
    """Video content types supported by Roku."""
    MOVIE = "movie"
    SHORT_FORM = "shortFormVideo"
    SERIES = "series"
    EPISODE = "episode"
    TV_SPECIAL = "tvSpecial"


class VideoQuality(Enum):
    """Video quality levels."""
    SD = "SD"
    HD = "HD"
    FHD = "FHD"
    UHD = "UHD"


@dataclass
class VideoFile:
    """Represents a video file with quality and URL information."""
    url: str
    quality: VideoQuality
    video_type: str = "HLS"  # HLS, MP4, DASH
    bitrate: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None

    def to_roku_content(self) -> Dict[str, Any]:
        """Convert to Roku content format."""
        return {
            "url": self.url,
            "quality": self.quality.value,
            "videoType": self.video_type
        }


@dataclass
class Thumbnail:
    """Represents a thumbnail image."""
    url: str
    width: int
    height: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "width": self.width,
            "height": self.height
        }


@dataclass
class Video:
    """Represents a video from Vimeo."""
    id: str
    title: str
    description: str
    duration: int  # in seconds
    created_time: datetime
    modified_time: datetime
    release_date: Optional[datetime] = None
    thumbnails: List[Thumbnail] = field(default_factory=list)
    video_files: List[VideoFile] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    privacy: str = "anybody"
    embed_html: Optional[str] = None
    link: Optional[str] = None
    plays: int = 0
    likes: int = 0

    # Vimeo-specific fields
    vimeo_uri: Optional[str] = None
    vimeo_embed_url: Optional[str] = None

    @classmethod
    def from_vimeo_response(cls, data: Dict[str, Any]) -> "Video":
        """Create a Video instance from Vimeo API response."""
        # Parse thumbnails
        thumbnails = []
        if "pictures" in data and "sizes" in data["pictures"]:
            for pic in data["pictures"]["sizes"]:
                thumbnails.append(Thumbnail(
                    url=pic.get("link", ""),
                    width=pic.get("width", 0),
                    height=pic.get("height", 0)
                ))

        # Parse video files
        video_files = []
        if "files" in data and data["files"]:
            for file_data in data["files"]:
                quality = cls._determine_quality(file_data.get("height", 0))
                video_files.append(VideoFile(
                    url=file_data.get("link", ""),
                    quality=quality,
                    video_type=file_data.get("type", "video/mp4").upper().replace("VIDEO/", ""),
                    width=file_data.get("width"),
                    height=file_data.get("height"),
                    bitrate=file_data.get("size")
                ))

        # Parse HLS if available
        if "play" in data and data["play"]:
            play_data = data["play"]
            if "hls" in play_data and play_data["hls"]:
                video_files.append(VideoFile(
                    url=play_data["hls"].get("link", ""),
                    quality=VideoQuality.HD,
                    video_type="HLS"
                ))

        # Parse tags
        tags = []
        if "tags" in data and data["tags"]:
            tags = [tag.get("name", "") for tag in data["tags"] if tag.get("name")]

        # Parse categories
        categories = []
        if "categories" in data and data["categories"]:
            categories = [cat.get("name", "") for cat in data["categories"] if cat.get("name")]

        # Parse dates
        created_time = cls._parse_datetime(data.get("created_time"))
        modified_time = cls._parse_datetime(data.get("modified_time"))
        release_date = cls._parse_datetime(data.get("release_time")) if data.get("release_time") else created_time

        return cls(
            id=data.get("uri", "").split("/")[-1] or str(data.get("resource_key", "")),
            title=data.get("name", "Untitled"),
            description=data.get("description", "") or "",
            duration=data.get("duration", 0),
            created_time=created_time,
            modified_time=modified_time,
            release_date=release_date,
            thumbnails=thumbnails,
            video_files=video_files,
            tags=tags,
            categories=categories,
            privacy=data.get("privacy", {}).get("view", "anybody"),
            embed_html=data.get("embed", {}).get("html"),
            link=data.get("link"),
            plays=data.get("stats", {}).get("plays", 0) or 0,
            likes=data.get("metadata", {}).get("connections", {}).get("likes", {}).get("total", 0) or 0,
            vimeo_uri=data.get("uri"),
            vimeo_embed_url=data.get("player_embed_url")
        )

    @staticmethod
    def _determine_quality(height: int) -> VideoQuality:
        """Determine video quality based on height."""
        if height >= 2160:
            return VideoQuality.UHD
        elif height >= 1080:
            return VideoQuality.FHD
        elif height >= 720:
            return VideoQuality.HD
        else:
            return VideoQuality.SD

    @staticmethod
    def _parse_datetime(date_str: Optional[str]) -> datetime:
        """Parse ISO format datetime string."""
        if not date_str:
            return datetime.now()
        try:
            # Handle Vimeo's ISO format
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return datetime.now()

    def get_best_thumbnail(self, min_width: int = 800) -> Optional[Thumbnail]:
        """Get the best thumbnail at or above the minimum width."""
        suitable = [t for t in self.thumbnails if t.width >= min_width]
        if suitable:
            return min(suitable, key=lambda t: t.width)
        elif self.thumbnails:
            return max(self.thumbnails, key=lambda t: t.width)
        return None

    def get_best_video_file(self) -> Optional[VideoFile]:
        """Get the highest quality video file, preferring HLS."""
        hls_files = [f for f in self.video_files if f.video_type == "HLS"]
        if hls_files:
            return hls_files[0]

        if self.video_files:
            quality_order = [VideoQuality.UHD, VideoQuality.FHD, VideoQuality.HD, VideoQuality.SD]
            for quality in quality_order:
                for file in self.video_files:
                    if file.quality == quality:
                        return file
            return self.video_files[0]
        return None


@dataclass
class RokuVideo:
    """Represents a video formatted for Roku Direct Publisher."""
    id: str
    title: str
    short_description: str
    long_description: str
    release_date: str
    duration: int
    thumbnail: str
    content: Dict[str, Any]
    tags: List[str] = field(default_factory=list)
    genres: List[str] = field(default_factory=list)
    video_type: VideoType = VideoType.SHORT_FORM
    rating: Optional[Dict[str, str]] = None

    @classmethod
    def from_video(cls, video: Video, video_type: VideoType = None) -> "RokuVideo":
        """Create a RokuVideo from a Video instance."""
        # Get best thumbnail
        thumbnail = video.get_best_thumbnail()
        thumbnail_url = thumbnail.url if thumbnail else ""

        # Get best video file
        video_file = video.get_best_video_file()

        # Build content object
        content = {
            "dateAdded": video.created_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration": video.duration,
            "videos": []
        }

        if video_file:
            content["videos"].append({
                "url": video_file.url,
                "quality": video_file.quality.value,
                "videoType": video_file.video_type
            })

        # Determine video type based on duration if not specified
        if video_type is None:
            # Short form is typically under 15 minutes
            if video.duration < 900:
                video_type = VideoType.SHORT_FORM
            else:
                video_type = VideoType.MOVIE

        # Truncate descriptions to Roku limits
        short_desc = video.description[:200] if video.description else video.title
        long_desc = video.description[:500] if video.description else video.title

        return cls(
            id=f"vimeo-{video.id}",
            title=video.title[:100],  # Roku title limit
            short_description=short_desc,
            long_description=long_desc,
            release_date=video.release_date.strftime("%Y-%m-%d") if video.release_date else video.created_time.strftime("%Y-%m-%d"),
            duration=video.duration,
            thumbnail=thumbnail_url,
            content=content,
            tags=video.tags[:20],  # Limit tags
            genres=video.categories[:5] if video.categories else ["Entertainment"],
            video_type=video_type
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to Roku feed dictionary format."""
        result = {
            "id": self.id,
            "title": self.title,
            "shortDescription": self.short_description,
            "longDescription": self.long_description,
            "releaseDate": self.release_date,
            "thumbnail": self.thumbnail,
            "content": self.content,
            "tags": self.tags,
            "genres": self.genres
        }

        if self.rating:
            result["rating"] = self.rating

        return result


@dataclass
class RokuFeed:
    """Represents a complete Roku Direct Publisher feed."""
    provider_name: str
    language: str = "en"
    last_updated: datetime = field(default_factory=datetime.now)
    short_form_videos: List[RokuVideo] = field(default_factory=list)
    movies: List[RokuVideo] = field(default_factory=list)
    series: List[Dict[str, Any]] = field(default_factory=list)
    tv_specials: List[RokuVideo] = field(default_factory=list)
    playlists: List[Dict[str, Any]] = field(default_factory=list)
    categories: List[Dict[str, Any]] = field(default_factory=list)

    def add_video(self, video: RokuVideo):
        """Add a video to the appropriate list based on its type."""
        if video.video_type == VideoType.SHORT_FORM:
            self.short_form_videos.append(video)
        elif video.video_type == VideoType.MOVIE:
            self.movies.append(video)
        elif video.video_type == VideoType.TV_SPECIAL:
            self.tv_specials.append(video)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to Roku feed dictionary format."""
        result = {
            "providerName": self.provider_name,
            "language": self.language,
            "lastUpdated": self.last_updated.strftime("%Y-%m-%dT%H:%M:%SZ")
        }

        if self.short_form_videos:
            result["shortFormVideos"] = [v.to_dict() for v in self.short_form_videos]

        if self.movies:
            result["movies"] = [v.to_dict() for v in self.movies]

        if self.series:
            result["series"] = self.series

        if self.tv_specials:
            result["tvSpecials"] = [v.to_dict() for v in self.tv_specials]

        if self.playlists:
            result["playlists"] = self.playlists

        if self.categories:
            result["categories"] = self.categories

        return result

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save(self, filepath: str):
        """Save feed to a JSON file."""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.to_json())
