import logging
import os
import time

import requests

logger = logging.getLogger(__name__)


def send_pdf(bot_token: str, chat_id: str, pdf_path: str, caption: str) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    filename = os.path.basename(pdf_path)

    for attempt in range(3):
        try:
            with open(pdf_path, "rb") as f:
                files = {"document": (filename, f, "application/pdf")}
                data = {"chat_id": chat_id, "caption": caption}
                response = requests.post(url, files=files, data=data, timeout=30)

            if response.status_code == 200:
                logger.info("PDF sent via Telegram: %s", filename)
                return True

            if response.status_code == 429:
                retry_after = response.json().get("parameters", {}).get("retry_after", 5)
                logger.warning("Telegram rate limited, waiting %ds", retry_after)
                time.sleep(retry_after)
                continue

            logger.error("Telegram sendDocument failed (%d): %s", response.status_code, response.text[:300])
            return False

        except requests.RequestException as e:
            logger.error("Telegram request failed (attempt %d/3): %s", attempt + 1, e)
            if attempt < 2:
                time.sleep(2)

    logger.error("All retries exhausted for Telegram PDF send")
    return False


def send_error_message(bot_token: str, chat_id: str, message: str) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    for attempt in range(3):
        try:
            data = {"chat_id": chat_id, "text": message}
            response = requests.post(url, json=data, timeout=10)

            if response.status_code == 200:
                logger.info("Error message sent via Telegram")
                return True

            if response.status_code == 429:
                retry_after = response.json().get("parameters", {}).get("retry_after", 5)
                logger.warning("Telegram rate limited, waiting %ds", retry_after)
                time.sleep(retry_after)
                continue

            logger.error("Telegram sendMessage failed (%d): %s", response.status_code, response.text[:300])
            return False

        except requests.RequestException as e:
            logger.error("Telegram request failed (attempt %d/3): %s", attempt + 1, e)
            if attempt < 2:
                time.sleep(2)

    logger.error("All retries exhausted for Telegram error message")
    return False
