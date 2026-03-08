import os
import pytest
from vis.config import Config, _mask


def test_mask_short_value():
    assert _mask("abc") == "***"


def test_mask_normal_value():
    assert _mask("my-secret-key-1234") == "***1234"


def test_load_missing_key(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="YOUTUBE_API_KEY"):
        Config.load()


def test_load_defaults(monkeypatch):
    env = {
        "YOUTUBE_API_KEY": "yt-key",
        "YOUTUBE_PLAYLIST_ID": "pl-id",
        "OPENROUTER_API_KEY": "or-key",
        "TELEGRAM_BOT_TOKEN": "tg-token",
        "TELEGRAM_CHAT_ID": "123",
        "DATABASE_URL": "postgresql://vis:pass@localhost:5432/vis",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    # Clear optional keys to test defaults
    monkeypatch.delenv("OUTPUT_DIR", raising=False)
    monkeypatch.delenv("MAX_VIDEOS", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("TRANSCRIPT_RETRY_DAYS", raising=False)

    config = Config.load()
    assert config.output_dir == "./output"
    assert config.max_videos == 100
    assert config.llm_model == "google/gemini-2.0-flash-001"
    assert config.transcript_retry_days == 3
