"""Manual-only CAPTCHA handling.

The human solves and submits the CAPTCHA in the browser. The application never
solves, bypasses or forwards the challenge; it only polls the DOM until the
query form becomes usable again, so no terminal interaction is required.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

logger = logging.getLogger("sat_tariff.captcha")

MANUAL_INSTRUCTIONS = (
    "CAPTCHA detectado. Resuélvelo manualmente y envíalo en el navegador.\n"
    "La extracción continuará automáticamente cuando la consulta quede habilitada."
)
WAITING_MESSAGE = "CAPTCHA detectado; esperando resolución manual en el navegador…"
RESOLVED_MESSAGE = "CAPTCHA resuelto; iniciando extracción automática."
ENTER_PROMPT = "Pulsa Enter para volver a revisar el navegador: "


class CaptchaTimeoutError(RuntimeError):
    """Raised when the human did not enable the query within the wait window."""


class CaptchaRequiredError(RuntimeError):
    """Raised when a CAPTCHA blocks progress and must be solved manually."""


def wait_for_manual_captcha_resolution(
    is_captcha_active: Callable[[], bool],
    is_query_enabled: Callable[[], bool] | None = None,
    *,
    timeout_seconds: float = 300.0,
    poll_interval: float = 1.0,
    require_enter: bool = False,
    prompt: Callable[[str], str] = input,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    announce: Callable[[str], None] | None = None,
) -> bool:
    """Poll the DOM until the CAPTCHA is gone and the query form is usable.

    ``input()`` is never called unless ``require_enter`` is explicitly enabled.
    """

    def _ready() -> bool:
        if is_captcha_active():
            return False
        return True if is_query_enabled is None else bool(is_query_enabled())

    if _ready():
        return True

    emit = announce if announce is not None else print
    emit(MANUAL_INSTRUCTIONS)
    emit(WAITING_MESSAGE)
    logger.warning("CAPTCHA detected. Manual resolution required in the browser; polling the DOM.")

    deadline = monotonic() + max(timeout_seconds, 0.0)
    while True:
        if _ready():
            emit(RESOLVED_MESSAGE)
            logger.info("CAPTCHA cleared and query enabled; continuing automatically.")
            return True
        if monotonic() >= deadline:
            break
        if require_enter:
            try:
                prompt(ENTER_PROMPT)
            except EOFError:
                logger.info("Interactive input unavailable; continuing with automatic polling only.")
                require_enter = False
        else:
            sleep(poll_interval)
    raise CaptchaTimeoutError(
        "La consulta no quedó habilitada dentro del tiempo configurado "
        f"({timeout_seconds:.0f}s). Resuelve el CAPTCHA en el navegador y reanuda con "
        "'python -m sat_tariff resume'."
    )
