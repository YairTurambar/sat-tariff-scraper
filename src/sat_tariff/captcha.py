"""Manual-only CAPTCHA handling."""

from __future__ import annotations

import logging
import time
from typing import Callable

logger = logging.getLogger("sat_tariff.captcha")


class CaptchaTimeoutError(RuntimeError):
    pass


class CaptchaRequiredError(RuntimeError):
    pass


def wait_for_manual_captcha_resolution(
    is_captcha_active: Callable[[], bool],
    *,
    prompt: Callable[[str], str] = input,
    poll_interval: float = 1.0,
    max_polls: int = 120,
) -> bool:
    logger.warning("CAPTCHA detected. Solve it manually in the browser. No OCR or bypass is attempted.")
    polls = 0
    while polls < max_polls:
        if not is_captcha_active():
            logger.info("CAPTCHA no longer visible; continuing.")
            return True
        try:
            prompt("Solve the CAPTCHA in the browser, then press Enter to re-check (or press Enter to keep polling): ")
        except EOFError:
            logger.info("Interactive input unavailable; falling back to polling only.")
        for _ in range(3):
            if not is_captcha_active():
                logger.info("CAPTCHA cleared after manual confirmation.")
                return True
            time.sleep(poll_interval)
            polls += 1
            if polls >= max_polls:
                break
    raise CaptchaTimeoutError("CAPTCHA was not cleared within the configured wait window.")
