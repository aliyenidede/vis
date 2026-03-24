import json
import logging
import time

import requests

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """You are a world-class knowledge writer. You receive a video transcript as RAW SOURCE MATERIAL. Your job is to extract the knowledge within it and produce a standalone educational briefing about the TOPIC — NOT a summary of the video.

CRITICAL DISTINCTION — internalize this deeply:
- WRONG: "In this video, the speaker discusses quantum computing. He first explains..."
- WRONG: "The presenter argues that AI safety is important. She then moves on to..."
- RIGHT: "Quantum computing exploits superposition and entanglement to solve problems that would take classical computers millennia. The fundamental unit, the qubit, differs from a classical bit in that..."
- RIGHT: "AI safety sits at the intersection of technical alignment and governance. The core challenge is ensuring that systems more capable than humans remain steerable..."

The reader should NEVER feel like they're reading a video recap. They should feel like they're reading a well-crafted article written by an expert who deeply understands the subject. They should finish reading and feel genuinely smarter about the topic.

The transcript may be in any language. Always produce your output in English.

Your writing principles:
- TEACH, DON'T SUMMARIZE: You are an educator, not a transcriber. Reorganize information by concept, not by video timeline.
- NEVER REFERENCE THE VIDEO: No "the speaker says", "this video covers", "the presenter explains". The knowledge stands alone.
- SOURCE FIDELITY: Only use information from the transcript. Don't invent facts. If the source is ambiguous, note the nuance.
- ENGAGING DEPTH: Write with intellectual energy. Use vivid analogies, concrete examples, and clear cause-effect chains. Make complex ideas click.
- STRUCTURE BY LOGIC: Group related ideas together. Build understanding progressively — context first, then mechanisms, then implications.
- BE SPECIFIC: No vague generalities. Every sentence should carry real information. "AI is transforming industries" is filler. "GPT-4 reduced legal document review time from 12 hours to 26 minutes at a Fortune 500 firm" is knowledge.

You MUST respond with valid JSON only, no markdown, no extra text. Use this exact structure:

{
  "headline": "A compelling, article-style title about the TOPIC (not the video title). Like a magazine headline that makes you want to read. Max 12 words.",
  "tldr": "2-3 sentences. What will the reader LEARN here? Frame as knowledge gained, not video content. Example: 'Retrieval-Augmented Generation combines search with language models to ground AI responses in verified facts, dramatically reducing hallucinations while maintaining fluency.'",
  "briefing": "4-6 substantial paragraphs. THIS IS THE CORE — write a standalone educational article about the topic.\n\nParagraph 1: Set the stage. Why does this topic matter? What problem or question does it address?\nParagraphs 2-4: The meat. Explain the key concepts, mechanisms, arguments, or findings. Use concrete examples, numbers, and analogies. Build understanding progressively.\nParagraph 5-6: So what? Implications, applications, what this means going forward. Connect to the bigger picture.\n\nWrite for an intelligent reader who is curious but not an expert. Make every paragraph earn its place.",
  "key_insights": ["5-8 specific, concrete takeaways. Each should be a complete thought that stands alone. NOT vague ('AI is important') but specific ('Fine-tuning a 7B parameter model on domain-specific data can match GPT-4 performance at 1/100th the inference cost')"],
  "analysis": {
    "why_it_matters": "2-3 sentences on the broader significance. Why should someone care about this topic? What does it change or challenge?",
    "critical_perspective": "2-3 sentences. What are the limitations, counterarguments, or blind spots? What should the reader question or watch out for?",
    "open_questions": ["2-3 genuinely interesting questions that this topic raises but doesn't fully answer. These should provoke further thinking."]
  },
  "infographic": {
    "topic": "The main subject in 3-5 words",
    "key_stats": ["2-4 notable numbers, statistics, or quantifiable claims from the content"],
    "key_terms": ["term: one-line definition (3-5 important concepts explained simply)"],
    "bottom_line": "One sentence — the single most important thing to remember"
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
        "max_tokens": 10000,
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
    required = {"briefing", "key_insights", "category"}
    if not isinstance(result, dict) or not required.issubset(result.keys()):
        # Backwards compat: accept old field names and remap
        if isinstance(result, dict) and "summary" in result:
            result.setdefault("briefing", result.pop("summary"))
        if isinstance(result, dict) and "key_ideas" in result:
            result.setdefault("key_insights", result.pop("key_ideas"))
        if not isinstance(result, dict) or not required.issubset(result.keys()):
            return False
    # Backfill optional fields
    result.setdefault("headline", "")
    result.setdefault("tldr", "")
    result.setdefault("infographic", {})
    result.setdefault("analysis", {})
    return True
