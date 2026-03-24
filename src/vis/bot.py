"""Telegram bot with commands for VIS pipeline management.

Commands:
    /start      - Welcome message and available commands
    /status     - Pipeline status and last run info
    /check      - Check for new videos without processing (no API credits used)
    /stats      - Detailed statistics (videos, API usage, DB counts)
    /run        - Trigger a pipeline run manually
    /pending    - List videos waiting for transcript retry
    /info       - System configuration and version info
    /addchannel - Add a YouTube channel to monitor
    /rmchannel  - Remove a monitored channel
    /channels   - List monitored channels
"""

import logging
import threading
import time

import requests

logger = logging.getLogger(__name__)

COMMANDS_HELP = """Available commands:

/status - Pipeline status and last run info
/check - Check for new videos (no API credits used)
/stats - Detailed statistics
/run - Trigger pipeline run
/pending - Videos waiting for transcript retry
/info - System configuration and version
/addchannel - Add a YouTube channel to monitor
/rmchannel - Remove a monitored channel
/channels - List monitored channels
"""

BOT_COMMANDS = [
    {"command": "status", "description": "Pipeline status and last run info"},
    {"command": "check", "description": "Check for new videos (no API credits)"},
    {"command": "stats", "description": "Detailed statistics"},
    {"command": "run", "description": "Trigger pipeline run"},
    {"command": "pending", "description": "Videos waiting for transcript retry"},
    {"command": "info", "description": "System configuration and version"},
    {"command": "addchannel", "description": "Add a YouTube channel to monitor"},
    {"command": "rmchannel", "description": "Remove a monitored channel"},
    {"command": "channels", "description": "List monitored channels"},
]


class VISBot:
    def __init__(self, bot_token: str, chat_id: str, db_pool, config):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.db_pool = db_pool
        self.config = config
        self._offset = 0
        self._running = False
        self._run_callback = None

    def set_run_callback(self, callback):
        self._run_callback = callback

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = {"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode}
        try:
            resp = requests.post(url, json=data, timeout=10)
            return resp.status_code == 200
        except requests.RequestException as e:
            logger.error("Failed to send message: %s", e)
            return False

    def _set_commands(self):
        """Register bot commands with Telegram so the menu button appears."""
        url = f"https://api.telegram.org/bot{self.bot_token}/setMyCommands"
        try:
            resp = requests.post(url, json={"commands": BOT_COMMANDS}, timeout=10)
            if resp.status_code == 200:
                logger.info("Bot menu commands registered")
            else:
                logger.warning("Failed to set bot commands: %s", resp.text)
        except requests.RequestException as e:
            logger.warning("Failed to set bot commands: %s", e)

    def start_polling(self):
        self._set_commands()
        self._running = True
        thread = threading.Thread(target=self._poll_loop, daemon=True)
        thread.start()
        logger.info("Telegram bot polling started")

    def stop_polling(self):
        self._running = False

    def _poll_loop(self):
        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        while self._running:
            try:
                resp = requests.get(
                    url,
                    params={"offset": self._offset, "timeout": 30},
                    timeout=35,
                )
                if resp.status_code != 200:
                    time.sleep(5)
                    continue

                data = resp.json()
                for update in data.get("result", []):
                    self._offset = update["update_id"] + 1
                    self._handle_update(update)

            except requests.RequestException:
                time.sleep(5)
            except Exception as e:
                logger.error("Bot poll error: %s", e, exc_info=True)
                time.sleep(5)

    def _handle_update(self, update: dict):
        message = update.get("message", {})
        text = message.get("text", "").strip()
        chat_id = str(message.get("chat", {}).get("id", ""))

        # Only respond to our configured chat
        if chat_id != self.chat_id:
            return

        if not text.startswith("/"):
            return

        command = text.split()[0].lower().split("@")[0]  # Handle /command@botname
        args = (
            text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
        )

        handlers = {
            "/start": self._cmd_start,
            "/status": self._cmd_status,
            "/check": self._cmd_check,
            "/stats": self._cmd_stats,
            "/run": self._cmd_run,
            "/pending": self._cmd_pending,
            "/info": self._cmd_info,
            "/addchannel": self._cmd_addchannel,
            "/rmchannel": self._cmd_rmchannel,
            "/channels": self._cmd_channels,
        }

        handler = handlers.get(command)
        if handler:
            try:
                handler(args)
            except Exception as e:
                logger.error("Command %s failed: %s", command, e, exc_info=True)
                self.send_message(f"Error: {e}", parse_mode=None)
        else:
            self.send_message(f"Unknown command: {command}\n\n{COMMANDS_HELP}")

    def _cmd_start(self, args=""):
        self.send_message(f"VIS Bot active.\n\n{COMMANDS_HELP}")

    def _cmd_status(self, args=""):
        from .db import get_pipeline_stats

        stats = get_pipeline_stats(self.db_pool)
        status_counts = stats["status_counts"]
        last_run = stats["last_run"]

        lines = ["*Pipeline Status*\n"]

        if last_run:
            lines.append(f"Last run: `{last_run['run_at']}`")
            lines.append(f"Videos processed: {last_run['videos_processed']}")
            lines.append(
                f"Telegram sent: {'Yes' if last_run['telegram_sent'] else 'No'}"
            )
        else:
            lines.append("No successful runs yet.")

        lines.append(f"\nTotal runs: {stats['total_runs']}")
        lines.append(f"Supadata calls this month: {stats['supadata_this_month']}/100")

        self.send_message("\n".join(lines))

    def _cmd_check(self, args=""):
        """Check for new videos without fetching transcripts (no API credits)."""
        from .youtube import fetch_playlist_videos
        from .db import get_processed_ids, get_retryable_videos

        self.send_message("Checking playlist for new videos...")

        try:
            all_videos = fetch_playlist_videos(
                self.config.youtube_playlist_id,
                self.config.max_videos,
            )
            processed_ids = get_processed_ids(self.db_pool)
            retryable = get_retryable_videos(
                self.db_pool, self.config.transcript_retry_days
            )
            retryable_ids = {v["video_id"] for v in retryable}

            new_videos = [v for v in all_videos if v["video_id"] not in processed_ids]
            retry_videos = [v for v in all_videos if v["video_id"] in retryable_ids]

            lines = [f"*Playlist Check* (no API credits used)\n"]
            lines.append(f"Total in playlist: {len(all_videos)}")
            lines.append(f"Already processed: {len(processed_ids)}")
            lines.append(f"New (unprocessed): {len(new_videos)}")
            lines.append(f"Pending retry: {len(retry_videos)}")

            if new_videos:
                lines.append("\n*New videos:*")
                for v in new_videos[:10]:
                    lines.append(f"  - {v['title']}")
                if len(new_videos) > 10:
                    lines.append(f"  ... and {len(new_videos) - 10} more")

            if retry_videos:
                lines.append("\n*Pending retry:*")
                for v in retry_videos[:5]:
                    r = next(
                        (rv for rv in retryable if rv["video_id"] == v["video_id"]), {}
                    )
                    lines.append(
                        f"  - {v['title']} (attempt {r.get('retry_count', 0)})"
                    )

            self.send_message("\n".join(lines))

        except Exception as e:
            self.send_message(f"Check failed: {e}")

    def _cmd_stats(self, args=""):
        from .db import get_pipeline_stats, get_api_usage_this_month

        stats = get_pipeline_stats(self.db_pool)
        supadata = get_api_usage_this_month(self.db_pool, "supadata")
        status_counts = stats["status_counts"]

        lines = ["*Detailed Statistics*\n"]

        lines.append("*Videos by status:*")
        for status, count in sorted(status_counts.items()):
            lines.append(f"  {status}: {count}")

        total_videos = sum(status_counts.values())
        lines.append(f"  Total: {total_videos}")

        lines.append(f"\n*API Usage (this month):*")
        lines.append(f"  Supadata calls: {supadata['total']}/100")
        lines.append(f"  Successful: {supadata['successful']}")
        remaining = max(0, 100 - supadata["total"])
        lines.append(f"  Remaining: {remaining}")

        lines.append(f"\n*Pipeline:*")
        lines.append(f"  Total runs: {stats['total_runs']}")
        if stats["last_run"]:
            lines.append(f"  Last run: `{stats['last_run']['run_at']}`")

        self.send_message("\n".join(lines))

    def _cmd_run(self, args=""):
        if self._run_callback:
            self.send_message("Triggering pipeline run...")
            try:
                thread = threading.Thread(target=self._run_callback, daemon=True)
                thread.start()
            except Exception as e:
                self.send_message(f"Run failed to start: {e}")
        else:
            self.send_message("Pipeline run callback not configured.")

    def _cmd_info(self, args=""):
        lines = ["*VIS — Video Insight System*\n"]
        lines.append("Version: `v0.4.0`")
        lines.append(f"LLM model: `{self.config.llm_model}`")
        lines.append(f"Playlist: `{self.config.youtube_playlist_id}`")
        lines.append(f"Max videos: {self.config.max_videos}")
        lines.append(f"Transcript retry: {self.config.transcript_retry_days} days")
        lines.append(f"Schedule: Daily at 08:00 (Istanbul)")
        lines.append(
            f"Supadata API: {'Configured' if self.config.supadata_api_key else 'Not configured'}"
        )

        self.send_message("\n".join(lines))

    def _cmd_pending(self, args=""):
        from .db import get_pending_videos

        pending = get_pending_videos(self.db_pool)

        if not pending:
            self.send_message("No videos pending retry.")
            return

        lines = [f"*Pending Videos* ({len(pending)} total)\n"]
        for v in pending[:15]:
            first_seen = v.get("first_seen_at")
            since = first_seen.strftime("%Y-%m-%d") if first_seen else "?"
            lines.append(f"  - {v['title']}")
            lines.append(f"    Retries: {v.get('retry_count', 0)} | Since: {since}")

        if len(pending) > 15:
            lines.append(f"\n... and {len(pending) - 15} more")

        self.send_message("\n".join(lines))

    def _cmd_addchannel(self, args=""):
        """Add a YouTube channel to monitor."""
        from .db import add_channel, remove_channel, update_channel_name
        from .youtube import fetch_channel_videos

        if not args:
            self.send_message("Usage: /addchannel <@handle or URL or channel ID>")
            return

        channel_input = args.strip()
        self.send_message(f"Adding channel: `{channel_input}`...")

        channel_id, is_new = add_channel(self.db_pool, channel_input)
        if channel_id is None:
            self.send_message(f"Channel `{channel_input}` is already being monitored.")
            return

        # Validate by test fetch
        videos, channel_name = fetch_channel_videos(channel_input, max_results=1)
        if channel_name is None:
            remove_channel(self.db_pool, channel_id)
            self.send_message(
                f"Failed to fetch channel `{channel_input}`. "
                "Check the URL/handle and try again."
            )
            return

        if channel_name:
            update_channel_name(self.db_pool, channel_id, channel_name)

        display = channel_name or channel_input
        self.send_message(
            f"Channel added: `{display}`\n"
            f"New videos will be processed in the next pipeline run."
        )

    def _cmd_rmchannel(self, args=""):
        """Remove a monitored channel."""
        from .db import get_active_channels, remove_channel

        if not args:
            self.send_message("Usage: /rmchannel <id or channel name>")
            return

        channels = get_active_channels(self.db_pool)
        if not channels:
            self.send_message("No channels are being monitored.")
            return

        arg = args.strip()
        matched = None

        # Try matching by ID (exact)
        try:
            target_id = int(arg)
            matched = next((c for c in channels if c["id"] == target_id), None)
        except ValueError:
            pass

        # Try matching by name or input (partial, case-insensitive)
        if not matched:
            arg_lower = arg.lower()
            matches = []
            for c in channels:
                name = (c.get("channel_name") or "").lower()
                inp = c["channel_input"].lower()
                if arg_lower in name or arg_lower in inp:
                    matches.append(c)

            if len(matches) == 1:
                matched = matches[0]
            elif len(matches) > 1:
                lines = [f"Multiple channels match `{arg}`. Use the ID:\n"]
                for c in matches:
                    display = c.get("channel_name") or c["channel_input"]
                    lines.append(f"  #{c['id']} — `{display}`")
                self.send_message("\n".join(lines))
                return

        if not matched:
            self.send_message(f"No channel matching `{arg}` found.")
            return

        remove_channel(self.db_pool, matched["id"])
        display = matched.get("channel_name") or matched["channel_input"]
        self.send_message(f"Channel removed: `{display}`")

    def _cmd_channels(self, args=""):
        """List monitored channels."""
        from .db import get_active_channels

        channels = get_active_channels(self.db_pool)

        if not channels:
            self.send_message("No channels are being monitored.")
            return

        lines = [f"*Monitored Channels* ({len(channels)})\n"]
        for c in channels:
            name = c.get("channel_name") or c["channel_input"]
            added = c["added_at"].strftime("%Y-%m-%d") if c.get("added_at") else "?"
            lines.append(f"  #{c['id']} — `{name}` (added {added})")

        self.send_message("\n".join(lines))
