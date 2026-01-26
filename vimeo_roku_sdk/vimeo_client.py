"""
Vimeo API client for fetching video content.
"""

import time
import logging
from typing import Optional, List, Dict, Any, Generator
from datetime import datetime
import requests

from .models import Video
from .config import VimeoConfig
from .exceptions import (
    VimeoAPIError,
    VimeoAuthError,
    VimeoRateLimitError
)

logger = logging.getLogger(__name__)


class VimeoClient:
    """
    Client for interacting with the Vimeo API.

    Handles authentication, pagination, rate limiting, and video retrieval.
    """

    BASE_URL = "https://api.vimeo.com"
    DEFAULT_PER_PAGE = 100  # Vimeo's max per page

    def __init__(
        self,
        access_token: str = None,
        client_id: str = None,
        client_secret: str = None,
        config: VimeoConfig = None
    ):
        """
        Initialize the Vimeo client.

        Args:
            access_token: Vimeo API access token
            client_id: Vimeo app client ID (optional, for generating tokens)
            client_secret: Vimeo app client secret (optional, for generating tokens)
            config: VimeoConfig object (alternative to individual parameters)
        """
        if config:
            self.access_token = config.access_token
            self.client_id = config.client_id
            self.client_secret = config.client_secret
            self._user_id = config.user_id
            self._folder_id = config.folder_id
            self._album_id = config.album_id
        else:
            self.access_token = access_token
            self.client_id = client_id
            self.client_secret = client_secret
            self._user_id = None
            self._folder_id = None
            self._album_id = None

        if not self.access_token:
            raise VimeoAuthError("Access token is required")

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.vimeo.*+json;version=3.4"
        })

        # Rate limiting
        self._last_request_time = 0
        self._min_request_interval = 0.1  # 100ms between requests

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Dict[str, Any] = None,
        data: Dict[str, Any] = None,
        retry_count: int = 3
    ) -> Dict[str, Any]:
        """
        Make a request to the Vimeo API with rate limiting and retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            data: Request body data
            retry_count: Number of retries on failure

        Returns:
            API response as dictionary

        Raises:
            VimeoAPIError: On API errors
            VimeoAuthError: On authentication errors
            VimeoRateLimitError: On rate limit errors
        """
        url = f"{self.BASE_URL}{endpoint}"

        # Rate limiting
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

        for attempt in range(retry_count):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=data,
                    timeout=30
                )

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    if attempt < retry_count - 1:
                        logger.warning(f"Rate limited, waiting {retry_after} seconds...")
                        time.sleep(retry_after)
                        continue
                    raise VimeoRateLimitError(
                        "Rate limit exceeded",
                        retry_after=retry_after
                    )

                # Handle authentication errors
                if response.status_code in (401, 403):
                    raise VimeoAuthError(
                        f"Authentication failed: {response.text}",
                        status_code=response.status_code
                    )

                # Handle other errors
                if response.status_code >= 400:
                    raise VimeoAPIError(
                        f"API request failed: {response.text}",
                        status_code=response.status_code,
                        response=response.json() if response.text else None
                    )

                return response.json() if response.text else {}

            except requests.exceptions.RequestException as e:
                if attempt < retry_count - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"Request failed, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                    continue
                raise VimeoAPIError(f"Request failed after {retry_count} attempts: {e}")

    def get_user(self, user_id: str = None) -> Dict[str, Any]:
        """
        Get user information.

        Args:
            user_id: User ID or 'me' for authenticated user

        Returns:
            User data dictionary
        """
        user_id = user_id or self._user_id or "me"
        return self._make_request("GET", f"/users/{user_id}")

    def get_video(self, video_id: str) -> Video:
        """
        Get a single video by ID.

        Args:
            video_id: Vimeo video ID

        Returns:
            Video object
        """
        # Request additional fields for full video information
        params = {
            "fields": "uri,name,description,duration,created_time,modified_time,"
                      "release_time,pictures,files,play,tags,categories,privacy,"
                      "embed,link,stats,metadata,player_embed_url"
        }
        data = self._make_request("GET", f"/videos/{video_id}", params=params)
        return Video.from_vimeo_response(data)

    def get_videos(
        self,
        user_id: str = None,
        per_page: int = None,
        page: int = 1,
        sort: str = "date",
        direction: str = "desc",
        filter_playable: bool = True
    ) -> Dict[str, Any]:
        """
        Get videos for a user.

        Args:
            user_id: User ID or 'me' for authenticated user
            per_page: Number of videos per page (max 100)
            page: Page number
            sort: Sort field (date, alphabetical, plays, likes, duration)
            direction: Sort direction (asc, desc)
            filter_playable: Only return videos that are playable

        Returns:
            API response with video data and pagination info
        """
        user_id = user_id or self._user_id or "me"
        per_page = min(per_page or self.DEFAULT_PER_PAGE, 100)

        params = {
            "per_page": per_page,
            "page": page,
            "sort": sort,
            "direction": direction,
            "fields": "uri,name,description,duration,created_time,modified_time,"
                      "release_time,pictures,files,play,tags,categories,privacy,"
                      "embed,link,stats,metadata,player_embed_url"
        }

        if filter_playable:
            params["filter"] = "playable"

        return self._make_request("GET", f"/users/{user_id}/videos", params=params)

    def iter_all_videos(
        self,
        user_id: str = None,
        sort: str = "date",
        direction: str = "desc",
        filter_playable: bool = True
    ) -> Generator[Video, None, None]:
        """
        Iterate over all videos for a user with automatic pagination.

        Args:
            user_id: User ID or 'me' for authenticated user
            sort: Sort field
            direction: Sort direction
            filter_playable: Only return playable videos

        Yields:
            Video objects
        """
        page = 1
        while True:
            response = self.get_videos(
                user_id=user_id,
                page=page,
                sort=sort,
                direction=direction,
                filter_playable=filter_playable
            )

            videos = response.get("data", [])
            if not videos:
                break

            for video_data in videos:
                yield Video.from_vimeo_response(video_data)

            # Check if there are more pages
            paging = response.get("paging", {})
            if not paging.get("next"):
                break

            page += 1
            logger.debug(f"Fetching page {page}...")

    def get_all_videos(
        self,
        user_id: str = None,
        sort: str = "date",
        direction: str = "desc",
        filter_playable: bool = True,
        limit: int = None
    ) -> List[Video]:
        """
        Get all videos for a user.

        Args:
            user_id: User ID or 'me' for authenticated user
            sort: Sort field
            direction: Sort direction
            filter_playable: Only return playable videos
            limit: Maximum number of videos to return

        Returns:
            List of Video objects
        """
        videos = []
        for video in self.iter_all_videos(user_id, sort, direction, filter_playable):
            videos.append(video)
            if limit and len(videos) >= limit:
                break
        return videos

    def get_album_videos(
        self,
        album_id: str = None,
        user_id: str = None,
        per_page: int = None,
        page: int = 1
    ) -> Dict[str, Any]:
        """
        Get videos from an album/showcase.

        Args:
            album_id: Album ID
            user_id: User ID or 'me' for authenticated user
            per_page: Number of videos per page
            page: Page number

        Returns:
            API response with video data
        """
        album_id = album_id or self._album_id
        if not album_id:
            raise VimeoAPIError("Album ID is required")

        user_id = user_id or self._user_id or "me"
        per_page = min(per_page or self.DEFAULT_PER_PAGE, 100)

        params = {
            "per_page": per_page,
            "page": page,
            "fields": "uri,name,description,duration,created_time,modified_time,"
                      "release_time,pictures,files,play,tags,categories,privacy,"
                      "embed,link,stats,metadata,player_embed_url"
        }

        return self._make_request(
            "GET",
            f"/users/{user_id}/albums/{album_id}/videos",
            params=params
        )

    def iter_album_videos(
        self,
        album_id: str = None,
        user_id: str = None
    ) -> Generator[Video, None, None]:
        """
        Iterate over all videos in an album with automatic pagination.

        Args:
            album_id: Album ID
            user_id: User ID

        Yields:
            Video objects
        """
        page = 1
        while True:
            response = self.get_album_videos(
                album_id=album_id,
                user_id=user_id,
                page=page
            )

            videos = response.get("data", [])
            if not videos:
                break

            for video_data in videos:
                yield Video.from_vimeo_response(video_data)

            paging = response.get("paging", {})
            if not paging.get("next"):
                break

            page += 1

    def get_folder_videos(
        self,
        folder_id: str = None,
        user_id: str = None,
        per_page: int = None,
        page: int = 1
    ) -> Dict[str, Any]:
        """
        Get videos from a folder/project.

        Args:
            folder_id: Folder/project ID
            user_id: User ID
            per_page: Number of videos per page
            page: Page number

        Returns:
            API response with video data
        """
        folder_id = folder_id or self._folder_id
        if not folder_id:
            raise VimeoAPIError("Folder ID is required")

        user_id = user_id or self._user_id or "me"
        per_page = min(per_page or self.DEFAULT_PER_PAGE, 100)

        params = {
            "per_page": per_page,
            "page": page,
            "fields": "uri,name,description,duration,created_time,modified_time,"
                      "release_time,pictures,files,play,tags,categories,privacy,"
                      "embed,link,stats,metadata,player_embed_url"
        }

        return self._make_request(
            "GET",
            f"/users/{user_id}/projects/{folder_id}/videos",
            params=params
        )

    def iter_folder_videos(
        self,
        folder_id: str = None,
        user_id: str = None
    ) -> Generator[Video, None, None]:
        """
        Iterate over all videos in a folder with automatic pagination.

        Args:
            folder_id: Folder ID
            user_id: User ID

        Yields:
            Video objects
        """
        page = 1
        while True:
            response = self.get_folder_videos(
                folder_id=folder_id,
                user_id=user_id,
                page=page
            )

            videos = response.get("data", [])
            if not videos:
                break

            for video_data in videos:
                yield Video.from_vimeo_response(video_data)

            paging = response.get("paging", {})
            if not paging.get("next"):
                break

            page += 1

    def get_videos_modified_since(
        self,
        since: datetime,
        user_id: str = None
    ) -> List[Video]:
        """
        Get videos modified since a specific date.

        Useful for incremental syncs.

        Args:
            since: Datetime to filter from
            user_id: User ID

        Returns:
            List of videos modified since the given date
        """
        videos = []
        for video in self.iter_all_videos(user_id=user_id, sort="date", direction="desc"):
            if video.modified_time < since:
                break
            videos.append(video)
        return videos

    def search_videos(
        self,
        query: str,
        user_id: str = None,
        per_page: int = None,
        page: int = 1
    ) -> Dict[str, Any]:
        """
        Search videos by query.

        Args:
            query: Search query
            user_id: User ID to search within
            per_page: Number of results per page
            page: Page number

        Returns:
            API response with search results
        """
        per_page = min(per_page or self.DEFAULT_PER_PAGE, 100)

        params = {
            "query": query,
            "per_page": per_page,
            "page": page,
            "fields": "uri,name,description,duration,created_time,modified_time,"
                      "release_time,pictures,files,play,tags,categories,privacy,"
                      "embed,link,stats,metadata,player_embed_url"
        }

        if user_id or self._user_id:
            endpoint = f"/users/{user_id or self._user_id or 'me'}/videos"
        else:
            endpoint = "/videos"

        return self._make_request("GET", endpoint, params=params)
