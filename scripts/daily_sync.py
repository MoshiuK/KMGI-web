#!/usr/bin/env python3
"""
Daily sync scheduler for Vimeo to Roku.

This script runs a sync job at a specified time each day.
It can be run as a daemon or as a systemd service.

Usage:
    python daily_sync.py                    # Run with default settings
    python daily_sync.py --time 06:00       # Run at 6 AM daily
    python daily_sync.py --once             # Run once and exit
    python daily_sync.py --config config.yaml  # Use custom config
"""

import argparse
import logging
import signal
import sys
import os
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from vimeo_roku_sdk import SyncManager, Config


def setup_logging(log_file: str = None, level: str = "INFO"):
    """Configure logging."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers
    )


def run_sync(config: Config, upload: bool = True, notify: bool = True) -> bool:
    """
    Run a single sync operation.

    Returns:
        True if sync was successful
    """
    logger = logging.getLogger(__name__)
    logger.info("Starting Vimeo to Roku sync...")

    try:
        manager = SyncManager(config=config)

        # Determine source based on config
        source = "all"
        if config.vimeo.album_id:
            source = "album"
        elif config.vimeo.folder_id:
            source = "folder"

        result = manager.sync(
            source=source,
            upload=upload,
            notify=notify
        )

        if result.success:
            logger.info(
                f"Sync completed successfully: "
                f"{result.videos_added} added, "
                f"{result.videos_skipped} skipped"
            )
            if result.feed_url:
                logger.info(f"Feed published to: {result.feed_url}")
        else:
            logger.error(f"Sync failed with {len(result.errors)} errors")
            for error in result.errors[:5]:
                logger.error(f"  - {error}")

        return result.success

    except Exception as e:
        logger.exception(f"Sync failed with exception: {e}")
        return False


def run_scheduler(config: Config, sync_time: str, upload: bool, notify: bool):
    """
    Run the scheduler that triggers sync at specified time.

    Args:
        config: Configuration object
        sync_time: Time to run sync (HH:MM format)
        upload: Whether to upload to S3
        notify: Whether to send webhook notification
    """
    try:
        import schedule
    except ImportError:
        print("Error: 'schedule' package is required for scheduled runs")
        print("Install with: pip install schedule")
        sys.exit(1)

    import time

    logger = logging.getLogger(__name__)
    logger.info(f"Starting scheduler. Sync will run daily at {sync_time}")

    # Define the job
    def sync_job():
        logger.info(f"Scheduled sync triggered at {datetime.now()}")
        run_sync(config, upload, notify)

    # Schedule the job
    schedule.every().day.at(sync_time).do(sync_job)

    # Handle graceful shutdown
    running = True

    def signal_handler(signum, frame):
        nonlocal running
        logger.info("Shutdown signal received. Stopping scheduler...")
        running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the scheduler
    logger.info("Scheduler is running. Press Ctrl+C to stop.")

    while running:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

    logger.info("Scheduler stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="Daily sync scheduler for Vimeo to Roku"
    )
    parser.add_argument(
        "-c", "--config",
        help="Path to configuration file (YAML)"
    )
    parser.add_argument(
        "-t", "--time",
        default="02:00",
        help="Time to run daily sync (HH:MM format, default: 02:00)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run sync once and exit (don't schedule)"
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Don't upload to S3"
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Don't send webhook notification"
    )
    parser.add_argument(
        "--log-file",
        help="Log file path"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_file, args.log_level)
    logger = logging.getLogger(__name__)

    # Load configuration
    if args.config:
        if not Path(args.config).exists():
            logger.error(f"Config file not found: {args.config}")
            sys.exit(1)
        config = Config.from_yaml_with_env(args.config)
    else:
        config = Config.from_env()

    # Validate configuration
    errors = config.validate()
    if errors:
        logger.error("Configuration errors:")
        for error in errors:
            logger.error(f"  - {error}")
        sys.exit(1)

    upload = not args.no_upload
    notify = not args.no_notify

    if args.once:
        # Run once and exit
        success = run_sync(config, upload, notify)
        sys.exit(0 if success else 1)
    else:
        # Run scheduler
        run_scheduler(config, args.time, upload, notify)


if __name__ == "__main__":
    main()
