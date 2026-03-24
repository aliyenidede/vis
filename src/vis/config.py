import os
import logging
from dataclasses import dataclass

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = {
    "OPENROUTER_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "DATABASE_URL",
    "SUPADATA_API_KEY",
}

REQUIRED_KEYS = [
    "YOUTUBE_PLAYLIST_ID",
    "OPENROUTER_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "DATABASE_URL",
]


def _mask(value: str) -> str:
    if len(value) <= 4:
        return "***"
    return "***" + value[-4:]


@dataclass
class Config:
    youtube_playlist_id: str
    openrouter_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    database_url: str
    output_dir: str
    max_videos: int
    llm_model: str
    transcript_retry_days: int
    supadata_api_key: str

    @classmethod
    def load(cls) -> "Config":
        load_dotenv()

        missing = [k for k in REQUIRED_KEYS if not os.getenv(k)]
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}"
            )

        config = cls(
            youtube_playlist_id=os.environ["YOUTUBE_PLAYLIST_ID"],
            openrouter_api_key=os.environ["OPENROUTER_API_KEY"],
            telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            telegram_chat_id=os.environ["TELEGRAM_CHAT_ID"],
            database_url=os.environ["DATABASE_URL"],
            output_dir=os.getenv("OUTPUT_DIR", "./output"),
            max_videos=int(os.getenv("MAX_VIDEOS", "100")),
            llm_model=os.getenv("LLM_MODEL", "deepseek/deepseek-v3.2"),
            transcript_retry_days=int(os.getenv("TRANSCRIPT_RETRY_DAYS", "3")),
            supadata_api_key=os.getenv("SUPADATA_API_KEY", ""),
        )

        logger.info("Configuration loaded successfully")
        for key in REQUIRED_KEYS:
            val = os.environ.get(key, "")
            if key in SENSITIVE_KEYS:
                logger.debug("  %s = %s", key, _mask(val))
            else:
                logger.debug("  %s = %s", key, val)

        return config
