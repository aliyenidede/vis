import logging
import re
import tempfile

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
    RequestBlocked,
)

logger = logging.getLogger(__name__)

MAX_TRANSCRIPT_LENGTH = 50000


def get_transcript(video_id: str) -> tuple:
    text, lang = _try_youtube_transcript_api(video_id)
    if text:
        return text, lang

    logger.info("Primary method failed for %s, trying yt-dlp fallback", video_id)
    text, lang = _try_yt_dlp(video_id)
    if text:
        return text, lang

    return None, None


def _try_youtube_transcript_api(video_id: str) -> tuple:
    ytt_api = YouTubeTranscriptApi()

    # Try specific languages in order
    for languages in [["en"], ["en-US", "en-GB"], ["tr"]]:
        try:
            transcript = ytt_api.fetch(video_id, languages=languages)
            text = " ".join(snippet.text for snippet in transcript.snippets)
            lang = languages[0]
            logger.info("Got transcript for %s via youtube-transcript-api (lang=%s)", video_id, lang)
            return _truncate(text), lang
        except (NoTranscriptFound, TranscriptsDisabled):
            continue
        except VideoUnavailable:
            logger.warning("Video unavailable: %s", video_id)
            return None, None
        except RequestBlocked:
            logger.warning("Request blocked for %s, will try yt-dlp", video_id)
            return None, None
        except Exception as e:
            logger.debug("youtube-transcript-api error for %s with %s: %s", video_id, languages, e)
            continue

    # Try listing all available transcripts
    try:
        transcript_list = ytt_api.list(video_id)
        # Try manual transcripts first
        for t in transcript_list:
            if not t.is_generated:
                try:
                    transcript = ytt_api.fetch(video_id, languages=[t.language_code])
                    text = " ".join(snippet.text for snippet in transcript.snippets)
                    logger.info("Got manual transcript for %s (lang=%s)", video_id, t.language_code)
                    return _truncate(text), t.language_code
                except Exception:
                    continue
        # Then auto-generated
        for t in transcript_list:
            if t.is_generated:
                try:
                    transcript = ytt_api.fetch(video_id, languages=[t.language_code])
                    text = " ".join(snippet.text for snippet in transcript.snippets)
                    logger.info("Got auto-generated transcript for %s (lang=%s)", video_id, t.language_code)
                    return _truncate(text), f"auto-{t.language_code}"
                except Exception:
                    continue
    except (TranscriptsDisabled, VideoUnavailable, RequestBlocked):
        pass
    except Exception as e:
        logger.debug("Failed to list transcripts for %s: %s", video_id, e)

    return None, None


def _try_yt_dlp(video_id: str) -> tuple:
    try:
        import yt_dlp
    except ImportError:
        logger.warning("yt-dlp not installed, skipping fallback")
        return None, None

    url = f"https://www.youtube.com/watch?v={video_id}"

    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en", "en-US", "en-GB", "tr"],
            "subtitlesformat": "vtt",
            "outtmpl": f"{tmpdir}/%(id)s.%(ext)s",
            "quiet": True,
            "no_warnings": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                # Check manual subtitles first, then automatic
                for sub_source in ["subtitles", "automatic_captions"]:
                    subs = info.get(sub_source, {})
                    for lang in ["en", "en-US", "en-GB", "tr"]:
                        if lang in subs:
                            # Download just this subtitle
                            ydl_opts_dl = {
                                "skip_download": True,
                                "writesubtitles": sub_source == "subtitles",
                                "writeautomaticsub": sub_source == "automatic_captions",
                                "subtitleslangs": [lang],
                                "subtitlesformat": "vtt",
                                "outtmpl": f"{tmpdir}/%(id)s.%(ext)s",
                                "quiet": True,
                                "no_warnings": True,
                            }
                            with yt_dlp.YoutubeDL(ydl_opts_dl) as ydl2:
                                ydl2.download([url])

                            # Find and parse the subtitle file
                            import glob
                            vtt_files = glob.glob(f"{tmpdir}/*.vtt")
                            if vtt_files:
                                text = _parse_vtt(vtt_files[0])
                                if text:
                                    prefix = "auto-" if sub_source == "automatic_captions" else ""
                                    logger.info("Got transcript via yt-dlp for %s (lang=%s%s)", video_id, prefix, lang)
                                    return _truncate(text), f"{prefix}{lang}"

                    # Try any available language
                    if subs:
                        lang = next(iter(subs))
                        ydl_opts_dl = {
                            "skip_download": True,
                            "writesubtitles": sub_source == "subtitles",
                            "writeautomaticsub": sub_source == "automatic_captions",
                            "subtitleslangs": [lang],
                            "subtitlesformat": "vtt",
                            "outtmpl": f"{tmpdir}/%(id)s.%(ext)s",
                            "quiet": True,
                            "no_warnings": True,
                        }
                        with yt_dlp.YoutubeDL(ydl_opts_dl) as ydl2:
                            ydl2.download([url])

                        import glob
                        vtt_files = glob.glob(f"{tmpdir}/*.vtt")
                        if vtt_files:
                            text = _parse_vtt(vtt_files[0])
                            if text:
                                prefix = "auto-" if sub_source == "automatic_captions" else ""
                                logger.info("Got transcript via yt-dlp for %s (lang=%s%s)", video_id, prefix, lang)
                                return _truncate(text), f"{prefix}{lang}"

        except Exception as e:
            logger.warning("yt-dlp failed for %s: %s", video_id, e)

    return None, None


def _parse_vtt(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Remove VTT header
    lines = content.split("\n")
    text_lines = []
    for line in lines:
        line = line.strip()
        # Skip timestamp lines, empty lines, WEBVTT header, NOTE lines
        if not line or line.startswith("WEBVTT") or line.startswith("NOTE"):
            continue
        if re.match(r"^\d{2}:\d{2}", line) and "-->" in line:
            continue
        if re.match(r"^\d+$", line):
            continue
        # Remove VTT tags
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            text_lines.append(line)

    # Deduplicate consecutive identical lines
    deduped = []
    for line in text_lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)

    return " ".join(deduped)


def _truncate(text: str) -> str:
    if len(text) > MAX_TRANSCRIPT_LENGTH:
        logger.info("Truncating transcript from %d to %d characters", len(text), MAX_TRANSCRIPT_LENGTH)
        return text[:MAX_TRANSCRIPT_LENGTH]
    return text
