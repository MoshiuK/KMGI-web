"""
Tests for data models.
"""

import pytest
from datetime import datetime
from vimeo_roku_sdk.models import (
    Video,
    RokuVideo,
    RokuFeed,
    VideoType,
    VideoQuality,
    Thumbnail,
    VideoFile
)


class TestVideo:
    """Tests for the Video model."""

    def test_from_vimeo_response_basic(self):
        """Test creating Video from minimal Vimeo response."""
        data = {
            "uri": "/videos/123456",
            "name": "Test Video",
            "description": "A test video",
            "duration": 120,
            "created_time": "2025-01-01T00:00:00Z",
            "modified_time": "2025-01-02T00:00:00Z"
        }

        video = Video.from_vimeo_response(data)

        assert video.id == "123456"
        assert video.title == "Test Video"
        assert video.description == "A test video"
        assert video.duration == 120

    def test_from_vimeo_response_with_pictures(self):
        """Test creating Video with thumbnail pictures."""
        data = {
            "uri": "/videos/123456",
            "name": "Test Video",
            "description": "",
            "duration": 120,
            "created_time": "2025-01-01T00:00:00Z",
            "modified_time": "2025-01-01T00:00:00Z",
            "pictures": {
                "sizes": [
                    {"link": "https://example.com/thumb_640.jpg", "width": 640, "height": 360},
                    {"link": "https://example.com/thumb_1280.jpg", "width": 1280, "height": 720}
                ]
            }
        }

        video = Video.from_vimeo_response(data)

        assert len(video.thumbnails) == 2
        assert video.thumbnails[0].width == 640
        assert video.thumbnails[1].width == 1280

    def test_get_best_thumbnail(self):
        """Test getting the best thumbnail."""
        video = Video(
            id="123",
            title="Test",
            description="",
            duration=100,
            created_time=datetime.now(),
            modified_time=datetime.now(),
            thumbnails=[
                Thumbnail(url="https://example.com/small.jpg", width=320, height=180),
                Thumbnail(url="https://example.com/medium.jpg", width=640, height=360),
                Thumbnail(url="https://example.com/large.jpg", width=1280, height=720)
            ]
        )

        # Get thumbnail at least 800px wide
        thumb = video.get_best_thumbnail(min_width=800)
        assert thumb.width == 1280

        # Get thumbnail at least 500px wide
        thumb = video.get_best_thumbnail(min_width=500)
        assert thumb.width == 640

    def test_determine_quality(self):
        """Test video quality determination."""
        assert Video._determine_quality(2160) == VideoQuality.UHD
        assert Video._determine_quality(1080) == VideoQuality.FHD
        assert Video._determine_quality(720) == VideoQuality.HD
        assert Video._determine_quality(480) == VideoQuality.SD


class TestRokuVideo:
    """Tests for the RokuVideo model."""

    def test_from_video(self):
        """Test converting Video to RokuVideo."""
        video = Video(
            id="123456",
            title="Test Video Title",
            description="This is a test video description",
            duration=300,
            created_time=datetime(2025, 1, 1, 0, 0, 0),
            modified_time=datetime(2025, 1, 2, 0, 0, 0),
            release_date=datetime(2025, 1, 1, 0, 0, 0),
            thumbnails=[
                Thumbnail(url="https://example.com/thumb.jpg", width=1280, height=720)
            ],
            video_files=[
                VideoFile(url="https://example.com/video.m3u8", quality=VideoQuality.HD, video_type="HLS")
            ],
            tags=["test", "demo"]
        )

        roku_video = RokuVideo.from_video(video)

        assert roku_video.id == "vimeo-123456"
        assert roku_video.title == "Test Video Title"
        assert roku_video.thumbnail == "https://example.com/thumb.jpg"
        assert roku_video.duration == 300
        assert "test" in roku_video.tags

    def test_to_dict(self):
        """Test converting RokuVideo to dictionary."""
        roku_video = RokuVideo(
            id="vimeo-123",
            title="Test",
            short_description="Short desc",
            long_description="Long description",
            release_date="2025-01-01",
            duration=120,
            thumbnail="https://example.com/thumb.jpg",
            content={"duration": 120, "videos": []},
            tags=["test"]
        )

        data = roku_video.to_dict()

        assert data["id"] == "vimeo-123"
        assert data["title"] == "Test"
        assert data["shortDescription"] == "Short desc"
        assert data["longDescription"] == "Long description"


class TestRokuFeed:
    """Tests for the RokuFeed model."""

    def test_add_short_form_video(self):
        """Test adding a short form video to feed."""
        feed = RokuFeed(provider_name="Test Provider")

        roku_video = RokuVideo(
            id="test-1",
            title="Test",
            short_description="Test",
            long_description="Test",
            release_date="2025-01-01",
            duration=60,
            thumbnail="https://example.com/thumb.jpg",
            content={},
            video_type=VideoType.SHORT_FORM
        )

        feed.add_video(roku_video)

        assert len(feed.short_form_videos) == 1
        assert len(feed.movies) == 0

    def test_add_movie(self):
        """Test adding a movie to feed."""
        feed = RokuFeed(provider_name="Test Provider")

        roku_video = RokuVideo(
            id="test-1",
            title="Test Movie",
            short_description="Test",
            long_description="Test",
            release_date="2025-01-01",
            duration=3600,
            thumbnail="https://example.com/thumb.jpg",
            content={},
            video_type=VideoType.MOVIE
        )

        feed.add_video(roku_video)

        assert len(feed.movies) == 1
        assert len(feed.short_form_videos) == 0

    def test_to_dict(self):
        """Test converting feed to dictionary."""
        feed = RokuFeed(
            provider_name="Test Provider",
            language="en"
        )

        data = feed.to_dict()

        assert data["providerName"] == "Test Provider"
        assert data["language"] == "en"
        assert "lastUpdated" in data

    def test_to_json(self):
        """Test converting feed to JSON string."""
        feed = RokuFeed(provider_name="Test Provider")

        json_str = feed.to_json()

        assert "Test Provider" in json_str
        assert "providerName" in json_str
