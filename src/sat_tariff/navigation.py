"""Browser-backed navigation and persistence orchestration."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re
import time
from typing import Callable

from bs4 import BeautifulSoup

from .browser import BrowserSession
from .captcha import CaptchaRequiredError, wait_for_manual_captcha_resolution
from .checkpoint import build_resume_point
from .config import AppConfig
from .extractors.nomenclature import parse_nomenclature
from .extractors.quotas import parse_quotas
from .extractors.restrictions import parse_restrictions
from .extractors.rights_taxes import parse_rights_taxes
from .models import HsCodeEntry, ProcessingState
from .selectors import CAPTCHA_INPUT_SELECTORS, SECTION_LABELS, SelectorBundle
from .storage import Storage

logger = logging.getLogger("sat_tariff.navigation")
SECTION_PARSERS: dict[str, Callable[[str], object]] = {
    "rights": parse_rights_taxes,
    "nomenclature": parse_nomenclature,
    "restrictions": parse_restrictions,
    "quotas": parse_quotas,
}
SECTION_PROGRESS = {
    "rights": ProcessingState.rights_completed,
    "nomenclature": ProcessingState.nomenclature_completed,
    "restrictions": ProcessingState.restrictions_completed,
    "quotas": ProcessingState.quotas_completed,
}


@dataclass(slots=True)
class NavigationService:
    config: AppConfig
    storage: Storage
    browser_session: BrowserSession

    def is_captcha_active(self) -> bool:
        page = self.browser_session.page
        return any(page.locator(selector).count() > 0 and page.locator(selector).first.is_visible() for selector in CAPTCHA_INPUT_SELECTORS)

    def ensure_captcha_cleared(self, code: str) -> None:
        if not self.is_captcha_active():
            return
        self.storage.update_state(code, ProcessingState.captcha_required, "CAPTCHA requires manual resolution")
        wait_for_manual_captcha_resolution(self.is_captcha_active)

    def _section_label(self, key: str) -> str:
        return SECTION_LABELS[key]

    def open_portal(self) -> None:
        self.browser_session.page.goto(self.config.sat_base_url)

    def search_hs_code(self, entry: HsCodeEntry) -> None:
        selectors = SelectorBundle(self.browser_session.page)
        input_locator = selectors.hs_code_input()
        input_locator.fill(entry.raw_code)
        self.ensure_captcha_cleared(entry.normalized_code)
        selectors.search_button().click()
        self.browser_session.page.wait_for_load_state("networkidle")
        self.ensure_captcha_cleared(entry.normalized_code)

    def _sanitize_html(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script"):
            script.decompose()
        cleaned = str(soup)
        cleaned = re.sub(r"(?i)(cookie|set-cookie|session(?:id)?|token)\s*[:=]\s*[^;\s]+", r"\1=[REDACTED]", cleaned)
        return cleaned

    def capture_evidence(self, code: str, section: str, error: Exception) -> None:
        artifacts_dir = Path(self.config.artifacts_dir)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        stamp = f"{code}-{section}-{int(time.time())}"
        page = self.browser_session.page
        try:
            page.screenshot(path=str(artifacts_dir / f"{stamp}.png"), full_page=True)
        except Exception:
            logger.debug("Screenshot capture failed for %s/%s", code, section)
        html = self._sanitize_html(page.content())
        (artifacts_dir / f"{stamp}.html").write_text(html, encoding="utf-8")
        (artifacts_dir / f"{stamp}.json").write_text(
            json.dumps({"code": code, "section": section, "error": str(error)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def open_section_html(self, section: str) -> str:
        label = self._section_label(section)
        page = self.browser_session.page
        trigger = SelectorBundle(page).section_trigger(label)
        with page.expect_popup() as popup_info:
            trigger.click()
        popup = popup_info.value
        popup.wait_for_load_state("networkidle")
        html = popup.content()
        popup.close()
        return html

    def process_code(self, entry: HsCodeEntry, *, force_restart: bool = False) -> None:
        row = self.storage.get_code(entry.normalized_code)
        if row is None:
            self.storage.upsert_code(entry.normalized_code, entry.raw_code, ProcessingState.pending)
            row = self.storage.get_code(entry.normalized_code)
        state_value = ProcessingState.pending.value if force_restart else row["state"]
        processed_sections = set() if force_restart else self.storage.get_processed_sections(entry.normalized_code)
        resume_point = build_resume_point(entry.normalized_code, state_value, processed_sections)
        if resume_point.next_section is None and not force_restart:
            return

        self.storage.update_state(entry.normalized_code, ProcessingState.in_progress)
        self.storage.record_attempt(entry.normalized_code)
        self.search_hs_code(entry)

        started = False
        for section in ("rights", "nomenclature", "restrictions", "quotas"):
            if not started and section != (resume_point.next_section or "rights"):
                continue
            started = True
            try:
                self.ensure_captcha_cleared(entry.normalized_code)
                html = self.open_section_html(section)
                result = SECTION_PARSERS[section](html)
                self.storage.save_section_rows(entry.normalized_code, section, result.rows, section_status=result.status)
                self.storage.update_state(entry.normalized_code, SECTION_PROGRESS[section])
            except CaptchaRequiredError as exc:
                self.storage.update_state(entry.normalized_code, ProcessingState.captcha_required, str(exc))
                raise
            except Exception as exc:
                self.capture_evidence(entry.normalized_code, section, exc)
                self.storage.update_state(entry.normalized_code, ProcessingState.retryable_error, str(exc))
                raise
        self.storage.update_state(entry.normalized_code, ProcessingState.completed)

    def process_entries(self, entries: list[HsCodeEntry], *, force_restart: bool = False) -> None:
        self.open_portal()
        for entry in entries:
            last_error: Exception | None = None
            for attempt in range(1, self.config.max_retries + 2):
                try:
                    self.process_code(entry, force_restart=force_restart)
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt > self.config.max_retries:
                        break
                    time.sleep(self.config.retry_backoff_factor * attempt)
            if last_error is not None:
                raise last_error
            if self.config.delay_between_codes_seconds > 0:
                time.sleep(self.config.delay_between_codes_seconds)



def run_navigation(entries: list[HsCodeEntry], config: AppConfig, storage: Storage, *, force_restart: bool = False) -> None:
    with BrowserSession(config) as browser_session:
        NavigationService(config=config, storage=storage, browser_session=browser_session).process_entries(entries, force_restart=force_restart)
