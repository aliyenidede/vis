import json
import logging
import time

import requests

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """You are a world-class video content analyst inspired by NotebookLM's approach: distill objective yet compelling insights strictly from the provided transcript. Never speculate or add information not present in the source material.

The transcript may be in any language. Always produce your output in English.

Your guiding principles:
- SOURCE FIDELITY: Only use information explicitly stated in the transcript. If something is ambiguous, say so.
- ENGAGING CLARITY: Write like an enthusiastic storyteller who also thinks like an analyst. Make it interesting but accurate.
- ACTIONABLE DEPTH: Every section should give the reader something concrete -- an insight, a fact, a takeaway.

You MUST respond with valid JSON only, no markdown, no extra text. Use this exact structure:

{
  "tldr": "A single paragraph (2-3 sentences max) that captures the essence of the video. Write it so someone can read it in 15 seconds and understand what the video is about and why it matters.",
  "summary": "3-5 paragraphs covering the full content of the video in detail. Structure it logically: context/problem first, then the core content, then conclusions or implications. Use clear topic sentences.",
  "key_ideas": ["idea 1", "idea 2", "... (5-8 concrete, specific takeaways, not vague generalities)"],
  "infographic": {
    "topic": "The main subject in 3-5 words",
    "key_stats": ["2-4 notable numbers, statistics, or quantifiable claims mentioned in the video"],
    "key_terms": ["term: one-line definition (3-5 important concepts explained simply)"],
    "bottom_line": "One sentence verdict -- the single most important thing to remember from this video"
  },
  "category": "One of: Tutorial, News, Analysis, Discussion, Review, Entertainment, Other"
}"""


def summarize_transcript(transcript: str, video_title: str, api_key: str, model: str) -> dict | None:
    user_prompt = f"Video title: {video_title}\n\nTranscript:\n{transcript}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    raw = _call_openrouter(messages, api_key, model)
    if raw is None:
        return None

    return _parse_llm_response(raw)


def _call_openrouter(messages: list, api_key: str, model: str, retries: int = 3) -> str | None:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 3000,
    }

    for attempt in range(retries):
        try:
            response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)

            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return content

            if response.status_code == 429:
                retry_after = int(response.headers.get("retry-after", 5 * (2 ** attempt)))
                logger.warning("Rate limited (429), waiting %ds (attempt %d/%d)", retry_after, attempt + 1, retries)
                time.sleep(retry_after)
                continue

            if response.status_code >= 500:
                wait = 2 * (attempt + 1)
                logger.warning("Server error %d, retrying in %ds (attempt %d/%d)",
                               response.status_code, wait, attempt + 1, retries)
                time.sleep(wait)
                continue

            # 4xx non-429
            logger.error("API error %d: %s", response.status_code, response.text[:500])
            return None

        except requests.RequestException as e:
            logger.error("Request failed (attempt %d/%d): %s", attempt + 1, retries, e)
            if attempt < retries - 1:
                time.sleep(2)

    logger.error("All %d retries exhausted for OpenRouter API call", retries)
    return None


def _strip_thinking(raw: str) -> str:
    """Strip <think>...</think> blocks from reasoning model output."""
    import re
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


def _parse_llm_response(raw: str) -> dict | None:
    raw = _strip_thinking(raw)

    # Strategy 1: direct parse
    try:
        result = json.loads(raw)
        if _validate_result(result):
            return result
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract from markdown code block
    import re
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(1))
            if _validate_result(result):
                return result
        except json.JSONDecodeError:
            pass

    # Strategy 3: find first { to last }
    first_brace = raw.find("{")
    last_brace = raw.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            result = json.loads(raw[first_brace:last_brace + 1])
            if _validate_result(result):
                return result
        except json.JSONDecodeError:
            pass

    logger.warning("Failed to parse LLM response: %s...", raw[:200])
    return None


def _validate_result(result: dict) -> bool:
    required = {"summary", "key_ideas", "category"}
    if not isinstance(result, dict) or not required.issubset(result.keys()):
        return False
    # Backfill optional fields for older/simpler models
    if "tldr" not in result:
        result["tldr"] = ""
    if "infographic" not in result:
        result["infographic"] = {}
    return True
