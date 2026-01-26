# Vimeo to Roku SDK

A Python SDK for syncing video content from Vimeo to Roku Direct Publisher channels. Automate your daily content updates and keep your Roku channel fresh with the latest videos from your Vimeo library.

## Features

- **Full Vimeo Integration**: Fetch videos from your entire library, specific albums, or folders
- **Roku Direct Publisher Support**: Generate JSON feeds compatible with Roku's specification
- **Automatic Classification**: Videos are automatically classified as short-form or movies based on duration
- **Incremental Sync**: Only process new or modified videos to save time
- **S3 Upload**: Optionally upload feeds directly to Amazon S3
- **Webhook Notifications**: Get notified when your feed is updated
- **Scheduled Syncs**: Run daily syncs automatically with the included scheduler
- **CLI & Library**: Use as a command-line tool or integrate into your own Python applications

## Installation

### From Source

```bash
git clone https://github.com/Knox-Media-Group/KMGI.git
cd KMGI
pip install -e .
```

### With Optional Dependencies

```bash
# For S3 upload support
pip install -e ".[s3]"

# For scheduled tasks
pip install -e ".[scheduler]"

# All optional dependencies
pip install -e ".[all]"
```

## Quick Start

### 1. Get Your Vimeo API Credentials

1. Go to [Vimeo Developer Apps](https://developer.vimeo.com/apps)
2. Create a new app or use an existing one
3. Generate an access token with the following scopes:
   - `public`
   - `private` (if you want to sync private videos)
   - `video_files` (required for video URLs)

### 2. Initialize Configuration

```bash
vimeo-roku init
```

This creates a `config.yaml` file. Edit it with your credentials:

```yaml
vimeo:
  access_token: "your_vimeo_access_token"

roku:
  provider_name: "Your Channel Name"
  feed_output_path: "./roku_feed.json"
```

### 3. Test Your Connection

```bash
vimeo-roku test --access-token YOUR_TOKEN
```

### 4. Run Your First Sync

```bash
vimeo-roku sync --config config.yaml
```

## CLI Usage

### Sync Videos

```bash
# Sync all videos
vimeo-roku sync --config config.yaml

# Sync from a specific album
vimeo-roku sync --config config.yaml --album ALBUM_ID

# Sync from a specific folder
vimeo-roku sync --config config.yaml --folder FOLDER_ID

# Incremental sync (only new/modified videos)
vimeo-roku sync --config config.yaml --incremental

# Sync and upload to S3
vimeo-roku sync --config config.yaml --upload

# Sync with webhook notification
vimeo-roku sync --config config.yaml --notify
```

### List Videos

```bash
# List first 20 videos
vimeo-roku list --access-token YOUR_TOKEN

# List more videos
vimeo-roku list --access-token YOUR_TOKEN --limit 100
```

### Validate Feed

```bash
vimeo-roku validate roku_feed.json
```

## Python Library Usage

### Basic Sync

```python
from vimeo_roku_sdk import SyncManager, Config

# Load configuration
config = Config.from_yaml("config.yaml")

# Create sync manager
manager = SyncManager(config=config)

# Run sync
result = manager.sync()

print(f"Added {result.videos_added} videos")
print(f"Feed saved to: {result.feed_path}")
```

### Custom Sync with Callbacks

```python
from vimeo_roku_sdk import SyncManager, Config

config = Config.from_yaml("config.yaml")
manager = SyncManager(config=config)

# Set progress callback
def on_progress(current, total):
    print(f"Processing {current}/{total}")

manager.set_callbacks(on_progress=on_progress)

# Sync from a specific album
result = manager.sync_album(album_id="12345678")
```

### Direct API Access

```python
from vimeo_roku_sdk import VimeoClient, RokuFeedGenerator

# Initialize clients
vimeo = VimeoClient(access_token="YOUR_TOKEN")
feed_gen = RokuFeedGenerator(provider_name="My Channel")

# Fetch videos
videos = vimeo.get_all_videos(limit=50)

# Add to feed
for video in videos:
    feed_gen.add_video(video)

# Save feed
feed_gen.save("roku_feed.json")

# Get stats
stats = feed_gen.get_stats()
print(f"Total videos: {stats['total_videos']}")
```

### Using Environment Variables

```python
from vimeo_roku_sdk import Config, SyncManager

# Load from environment variables
config = Config.from_env()

# Or load from YAML with env var overrides
config = Config.from_yaml_with_env("config.yaml")

manager = SyncManager(config=config)
result = manager.sync()
```

## Daily Sync Scheduler

Run automatic daily syncs using the included scheduler:

```bash
# Run sync at 2 AM daily
python scripts/daily_sync.py --config config.yaml --time 02:00

# Run once (for testing or cron jobs)
python scripts/daily_sync.py --config config.yaml --once
```

### Using Cron

Add to your crontab (`crontab -e`):

```cron
# Run daily at 2 AM
0 2 * * * cd /path/to/KMGI && python scripts/daily_sync.py --config config.yaml --once >> /var/log/vimeo-roku.log 2>&1
```

### Using Systemd

Create `/etc/systemd/system/vimeo-roku-sync.service`:

```ini
[Unit]
Description=Vimeo to Roku Sync Service
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/KMGI
ExecStart=/usr/bin/python3 scripts/daily_sync.py --config config.yaml --time 02:00
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable vimeo-roku-sync
sudo systemctl start vimeo-roku-sync
```

## Configuration Reference

### Vimeo Settings

| Setting | Description | Required |
|---------|-------------|----------|
| `access_token` | Vimeo API access token | Yes |
| `user_id` | Specific user ID (default: authenticated user) | No |
| `folder_id` | Sync only from this folder | No |
| `album_id` | Sync only from this album | No |

### Roku Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `provider_name` | Channel provider name | Required |
| `language` | Feed language (ISO 639-1) | `en` |
| `feed_output_path` | Output path for feed | `./roku_feed.json` |
| `default_genre` | Default genre for videos | `Entertainment` |
| `rating_system` | Content rating system | `USA_TV` |
| `default_rating` | Default content rating | `TV-G` |
| `s3_bucket` | S3 bucket for upload | None |
| `s3_key` | S3 object key | `roku-feed.json` |
| `webhook_url` | Webhook URL for notifications | None |

### Sync Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `include_private` | Include private videos | `false` |
| `min_duration` | Minimum duration (seconds) | `0` |
| `max_duration` | Maximum duration (seconds) | None |
| `include_tags` | Only include videos with tags | `[]` |
| `exclude_tags` | Exclude videos with tags | `[]` |
| `short_form_max_duration` | Threshold for short-form | `900` (15 min) |
| `cache_enabled` | Enable sync state caching | `true` |

## Roku Feed Format

The generated feed follows Roku's Direct Publisher specification:

```json
{
  "providerName": "Your Channel",
  "language": "en",
  "lastUpdated": "2025-01-26T12:00:00Z",
  "shortFormVideos": [
    {
      "id": "vimeo-123456",
      "title": "Video Title",
      "shortDescription": "Brief description",
      "thumbnail": "https://...",
      "releaseDate": "2025-01-01",
      "content": {
        "dateAdded": "2025-01-01T00:00:00Z",
        "duration": 300,
        "videos": [
          {
            "url": "https://...",
            "quality": "HD",
            "videoType": "HLS"
          }
        ]
      }
    }
  ],
  "movies": [...],
  "series": [...]
}
```

## Troubleshooting

### "Access token is required"

Make sure you have set your Vimeo access token in the config file or environment:

```bash
export VIMEO_ACCESS_TOKEN=your_token_here
```

### "No video content URLs provided"

Your Vimeo account may not have access to video file URLs. Ensure:
1. Your access token has the `video_files` scope
2. Your Vimeo plan supports file access (Pro, Business, or Premium)

### "Feed validation errors"

Run the validation command to see specific issues:

```bash
vimeo-roku validate roku_feed.json
```

### Videos Not Appearing

Check if videos are being filtered:
- Private videos are excluded by default
- Very short videos may not meet minimum duration
- Check `include_tags` and `exclude_tags` settings

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see LICENSE file for details.

## Support

- **Issues**: [GitHub Issues](https://github.com/Knox-Media-Group/KMGI/issues)
- **Documentation**: [Roku Direct Publisher Docs](https://developer.roku.com/docs/specs/direct-publisher-feed-specs/json-dp-spec.md)
- **Vimeo API**: [Vimeo Developer Documentation](https://developer.vimeo.com/api/reference)
