"""
Command-line interface for the Vimeo to Roku SDK.
"""

import argparse
import logging
import sys
import os
from pathlib import Path
from datetime import datetime

from .config import Config
from .sync_manager import SyncManager, create_sync_manager
from .vimeo_client import VimeoClient
from .roku_feed import RokuFeedGenerator


def setup_logging(level: str = "INFO", log_file: str = None):
    """Configure logging for the CLI."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers
    )


def print_progress(current: int, total: int):
    """Print a progress indicator."""
    percentage = (current / total) * 100 if total > 0 else 0
    bar_length = 40
    filled = int(bar_length * current / total) if total > 0 else 0
    bar = "=" * filled + "-" * (bar_length - filled)
    print(f"\rProgress: [{bar}] {percentage:.1f}% ({current}/{total})", end="", flush=True)
    if current >= total:
        print()  # New line when complete


def cmd_sync(args):
    """Execute the sync command."""
    print("Vimeo to Roku Sync")
    print("=" * 50)

    # Load configuration
    if args.config:
        print(f"Loading configuration from: {args.config}")
        config = Config.from_yaml_with_env(args.config)
    else:
        # Use environment variables
        config = Config.from_env()

    # Override with command line arguments
    if args.access_token:
        config.vimeo.access_token = args.access_token
    if args.provider_name:
        config.roku.provider_name = args.provider_name
    if args.output:
        config.roku.feed_output_path = args.output

    # Validate configuration
    errors = config.validate()
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    # Setup logging
    setup_logging(config.sync.log_level, config.sync.log_file)

    # Create sync manager
    manager = SyncManager(config=config)

    # Set progress callback if not quiet
    if not args.quiet:
        manager.set_callbacks(on_progress=print_progress)

    print(f"Provider: {config.roku.provider_name}")
    print(f"Output: {config.roku.feed_output_path}")
    print()

    # Determine source
    source = "all"
    album_id = args.album
    folder_id = args.folder

    if album_id:
        source = "album"
        print(f"Syncing from album: {album_id}")
    elif folder_id:
        source = "folder"
        print(f"Syncing from folder: {folder_id}")
    else:
        print("Syncing all videos")

    print()

    # Run sync
    result = manager.sync(
        source=source,
        album_id=album_id,
        folder_id=folder_id,
        incremental=args.incremental,
        upload=args.upload,
        notify=args.notify
    )

    # Print results
    print()
    print("Sync Results")
    print("-" * 30)
    print(f"Status: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"Videos processed: {result.videos_processed}")
    print(f"Videos added: {result.videos_added}")
    print(f"Videos skipped: {result.videos_skipped}")
    print(f"Videos failed: {result.videos_failed}")
    print(f"Duration: {result.duration_seconds:.2f} seconds")

    if result.feed_path:
        print(f"Feed saved to: {result.feed_path}")
    if result.feed_url:
        print(f"Feed URL: {result.feed_url}")

    if result.errors:
        print()
        print("Errors:")
        for error in result.errors[:10]:
            print(f"  - {error}")
        if len(result.errors) > 10:
            print(f"  ... and {len(result.errors) - 10} more")

    return 0 if result.success else 1


def cmd_validate(args):
    """Validate an existing feed file."""
    print(f"Validating feed: {args.feed_file}")

    if not Path(args.feed_file).exists():
        print(f"Error: File not found: {args.feed_file}")
        return 1

    import json
    try:
        with open(args.feed_file, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON - {e}")
        return 1

    # Basic validation
    errors = []

    if "providerName" not in data:
        errors.append("Missing required field: providerName")

    if "lastUpdated" not in data:
        errors.append("Missing required field: lastUpdated")

    # Check for content
    content_types = ["shortFormVideos", "movies", "series", "tvSpecials"]
    has_content = any(data.get(ct) for ct in content_types)

    if not has_content:
        errors.append("Feed has no content (no videos, movies, or series)")

    # Validate videos
    for content_type in content_types:
        items = data.get(content_type, [])
        for idx, item in enumerate(items):
            prefix = f"{content_type}[{idx}]"
            if not item.get("id"):
                errors.append(f"{prefix}: Missing 'id'")
            if not item.get("title"):
                errors.append(f"{prefix}: Missing 'title'")
            if not item.get("thumbnail"):
                errors.append(f"{prefix}: Missing 'thumbnail'")

    if errors:
        print()
        print(f"Found {len(errors)} validation issue(s):")
        for error in errors:
            print(f"  - {error}")
        return 1
    else:
        print("Feed is valid!")

        # Print stats
        print()
        print("Feed Statistics:")
        print(f"  Provider: {data.get('providerName')}")
        print(f"  Last Updated: {data.get('lastUpdated')}")
        print(f"  Short Form Videos: {len(data.get('shortFormVideos', []))}")
        print(f"  Movies: {len(data.get('movies', []))}")
        print(f"  Series: {len(data.get('series', []))}")
        print(f"  TV Specials: {len(data.get('tvSpecials', []))}")

        return 0


def cmd_list_videos(args):
    """List videos from Vimeo."""
    print("Fetching videos from Vimeo...")

    # Get access token
    access_token = args.access_token or os.getenv("VIMEO_ACCESS_TOKEN")
    if not access_token:
        print("Error: Vimeo access token is required")
        print("Set VIMEO_ACCESS_TOKEN environment variable or use --access-token")
        return 1

    client = VimeoClient(access_token=access_token)

    try:
        videos = client.get_all_videos(limit=args.limit)
    except Exception as e:
        print(f"Error fetching videos: {e}")
        return 1

    print(f"\nFound {len(videos)} videos:\n")

    for idx, video in enumerate(videos, 1):
        duration_min = video.duration // 60
        duration_sec = video.duration % 60
        print(f"{idx}. {video.title}")
        print(f"   ID: {video.id}")
        print(f"   Duration: {duration_min}:{duration_sec:02d}")
        print(f"   Created: {video.created_time.strftime('%Y-%m-%d')}")
        if video.tags:
            print(f"   Tags: {', '.join(video.tags[:5])}")
        print()

    return 0


def cmd_test_connection(args):
    """Test connections to Vimeo API."""
    print("Testing Vimeo API Connection")
    print("=" * 40)

    access_token = args.access_token or os.getenv("VIMEO_ACCESS_TOKEN")
    if not access_token:
        print("Error: Vimeo access token is required")
        return 1

    try:
        client = VimeoClient(access_token=access_token)
        user = client.get_user()

        print(f"✓ Connected to Vimeo API")
        print(f"  User: {user.get('name')}")
        print(f"  Account: {user.get('account')}")
        print(f"  Videos: {user.get('metadata', {}).get('connections', {}).get('videos', {}).get('total', 'N/A')}")

        return 0

    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return 1


def cmd_init_config(args):
    """Generate a sample configuration file."""
    config_content = '''# Vimeo to Roku SDK Configuration

vimeo:
  # Required: Your Vimeo API access token
  # Get one at: https://developer.vimeo.com/apps
  access_token: ""

  # Optional: Vimeo user ID (leave empty to use authenticated user)
  user_id: ""

  # Optional: Sync only from a specific folder/project
  folder_id: ""

  # Optional: Sync only from a specific album/showcase
  album_id: ""

roku:
  # Required: Your Roku channel provider name
  provider_name: "Your Channel Name"

  # Optional: Roku channel ID
  channel_id: ""

  # Feed language (ISO 639-1 code)
  language: "en"

  # Where to save the generated feed
  feed_output_path: "./roku_feed.json"

  # Default genre for videos without categories
  default_genre: "Entertainment"

  # Content rating system (USA_TV, MPAA, etc.)
  rating_system: "USA_TV"
  default_rating: "TV-G"

  # Optional: S3 bucket for feed hosting
  # s3_bucket: "your-bucket-name"
  # s3_key: "feeds/roku-feed.json"

  # Optional: Webhook URL to notify when feed is updated
  # webhook_url: "https://your-server.com/webhook"

sync:
  # Include private videos (not recommended)
  include_private: false

  # Minimum video duration in seconds (0 = no minimum)
  min_duration: 0

  # Maximum video duration in seconds (null = no maximum)
  # max_duration: 3600

  # Only include videos with these tags (empty = include all)
  include_tags: []

  # Exclude videos with these tags
  exclude_tags: []

  # Videos shorter than this are "short form", longer are "movies"
  short_form_max_duration: 900  # 15 minutes

  # Enable caching for incremental syncs
  cache_enabled: true
  cache_path: "./.vimeo_roku_cache"

  # Logging configuration
  log_level: "INFO"
  # log_file: "./sync.log"
'''

    output_path = args.output or "config.yaml"

    if Path(output_path).exists() and not args.force:
        print(f"Error: {output_path} already exists. Use --force to overwrite.")
        return 1

    with open(output_path, "w") as f:
        f.write(config_content)

    print(f"Configuration file created: {output_path}")
    print()
    print("Next steps:")
    print("1. Edit the config file and add your Vimeo access token")
    print("2. Set your Roku provider name")
    print("3. Run: vimeo-roku sync --config config.yaml")

    return 0


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="vimeo-roku",
        description="Sync videos from Vimeo to Roku Direct Publisher"
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Sync command
    sync_parser = subparsers.add_parser("sync", help="Sync videos from Vimeo to Roku")
    sync_parser.add_argument(
        "-c", "--config",
        help="Path to configuration file (YAML)"
    )
    sync_parser.add_argument(
        "-t", "--access-token",
        help="Vimeo API access token (overrides config)"
    )
    sync_parser.add_argument(
        "-p", "--provider-name",
        help="Roku provider name (overrides config)"
    )
    sync_parser.add_argument(
        "-o", "--output",
        help="Output path for feed JSON (overrides config)"
    )
    sync_parser.add_argument(
        "--album",
        help="Sync only from this Vimeo album ID"
    )
    sync_parser.add_argument(
        "--folder",
        help="Sync only from this Vimeo folder ID"
    )
    sync_parser.add_argument(
        "--incremental",
        action="store_true",
        help="Only sync videos modified since last sync"
    )
    sync_parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload feed to S3 after generating"
    )
    sync_parser.add_argument(
        "--notify",
        action="store_true",
        help="Send webhook notification after sync"
    )
    sync_parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress progress output"
    )
    sync_parser.set_defaults(func=cmd_sync)

    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate a Roku feed file")
    validate_parser.add_argument(
        "feed_file",
        help="Path to the feed JSON file to validate"
    )
    validate_parser.set_defaults(func=cmd_validate)

    # List command
    list_parser = subparsers.add_parser("list", help="List videos from Vimeo")
    list_parser.add_argument(
        "-t", "--access-token",
        help="Vimeo API access token"
    )
    list_parser.add_argument(
        "-l", "--limit",
        type=int,
        default=20,
        help="Maximum number of videos to list (default: 20)"
    )
    list_parser.set_defaults(func=cmd_list_videos)

    # Test command
    test_parser = subparsers.add_parser("test", help="Test API connections")
    test_parser.add_argument(
        "-t", "--access-token",
        help="Vimeo API access token"
    )
    test_parser.set_defaults(func=cmd_test_connection)

    # Init command
    init_parser = subparsers.add_parser("init", help="Generate a sample configuration file")
    init_parser.add_argument(
        "-o", "--output",
        default="config.yaml",
        help="Output path for config file (default: config.yaml)"
    )
    init_parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Overwrite existing config file"
    )
    init_parser.set_defaults(func=cmd_init_config)

    # Parse arguments
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Execute command
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
