"""Browser-backed navigation and persistence orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import re
import time
from typing import Callable

from bs4 import BeautifulSoup

from .browser import BrowserSession
from .captcha import CaptchaRequiredError, CaptchaTimeoutError, wait_for_manual_captcha_resolution
from .checkpoint import build_resume_point
from .config import AppConfig
from .extractors.nomenclature import parse_nomenclature
from .extractors.quotas import parse_quotas
from .extractors.restrictions import parse_restrictions
from .extractors.rights_taxes import parse_rights_taxes
from .models import HsCodeEntry, ProcessingState
from .selectors import (
    CAPTCHA_INPUT_SELECTORS,
    HS_CODE_INPUT_SELECTORS,
    SAT_FORM_SELECTOR,
    SECTION_LABELS,
    SelectorBundle,
    find_form_context,
    section_submit_selectors,
)
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
SECTION_SEQUENCE = ("rights", "nomenclature", "restrictions", "quotas")

PREPARE_SECTION_SUBMIT_SCRIPT = """
(args) => {
  const form = document.querySelector(args.formSelector);
  if (!form) {
    return {ok: false, reason: 'form-not-found'};
  }
  const candidates = Array.from(form.querySelectorAll("input[type='submit'], input[type='button'], button"));
  const labelOf = (el) => ((el.value || el.textContent || '').trim());
  let button = candidates.find((el) => labelOf(el) === args.label);
  if (!button) {
    button = candidates.find((el) => labelOf(el).toLowerCase().includes(args.label.toLowerCase()));
  }
  if (!button) {
    return {ok: false, reason: 'section-button-not-found'};
  }
  const hidden = document.createElement('input');
  hidden.type = 'hidden';
  hidden.name = button.name || button.id || args.label;
  hidden.value = button.value || args.label;
  hidden.setAttribute('data-sat-marker', args.marker);
  form.appendChild(hidden);
  const previousTarget = form.target || '';
  form.target = args.target;
  return {ok: true, previousTarget: previousTarget, name: hidden.name, value: hidden.value};
}
"""

SUBMIT_FORM_SCRIPT = """
(args) => {
  const form = document.querySelector(args.formSelector);
  if (!form) {
    return false;
  }
  form.submit();
  return true;
}
"""

RESTORE_FORM_SCRIPT = """
(args) => {
  const form = document.querySelector(args.formSelector);
  if (!form) {
    return false;
  }
  form.target = args.previousTarget || '';
  const marker = form.querySelector(`[data-sat-marker='${args.marker}']`);
  if (marker) {
    marker.remove();
  }
  return true;
}
"""


class FormNotAvailableError(RuntimeError):
    """Raised when the ``frmBuscar`` query form could not be used."""


class SectionNavigationError(RuntimeError):
    """Raised when a result section could not be opened."""


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


@dataclass(slots=True)
class NavigationService:
    config: AppConfig
    storage: Storage
    browser_session: BrowserSession
    announce: Callable[[str], None] = print
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic
    _portal_opened: bool = field(default=False, init=False)
    _section_counter: int = field(default=0, init=False)

    # -- context helpers -------------------------------------------------
    def form_context(self):
        """Return the page or frame that owns ``frmBuscar``."""

        return find_form_context(self.browser_session.page)

    def selectors(self) -> SelectorBundle:
        return SelectorBundle(self.form_context())

    def has_form(self) -> bool:
        context = self.form_context()
        try:
            return context.locator(SAT_FORM_SELECTOR).count() > 0
        except Exception:  # pragma: no cover - defensive
            return False

    # -- CAPTCHA ---------------------------------------------------------
    def is_captcha_active(self) -> bool:
        context = self.form_context()
        for selector in CAPTCHA_INPUT_SELECTORS:
            try:
                locator = context.locator(selector)
                if locator.count() > 0 and locator.first.is_visible():
                    return True
            except Exception:  # pragma: no cover - defensive
                continue
        return False

    def is_query_enabled(self) -> bool:
        bundle = self.selectors()
        if not bundle.has_any(HS_CODE_INPUT_SELECTORS):
            return False
        locator = bundle.hs_code_input()
        try:
            return bool(locator.is_visible() and locator.is_enabled() and locator.is_editable())
        except Exception:  # pragma: no cover - defensive
            return False

    def ensure_captcha_cleared(self, code: str) -> bool:
        """Wait for a manual CAPTCHA resolution when one is on screen.

        Returns ``True`` when a wait was required. The CAPTCHA state is a pause,
        never a permanent error: previously persisted sections stay untouched.
        """

        if not self.is_captcha_active():
            return False
        self.storage.update_state(code, ProcessingState.captcha_required, "CAPTCHA requires manual resolution")
        wait_for_manual_captcha_resolution(
            self.is_captcha_active,
            self.is_query_enabled,
            timeout_seconds=self.config.captcha_timeout_seconds,
            poll_interval=self.config.captcha_poll_interval_seconds,
            require_enter=self.config.captcha_require_enter,
            sleep=self.sleep,
            monotonic=self.monotonic,
            announce=self.announce,
        )
        self.storage.update_state(code, ProcessingState.in_progress)
        return True

    # -- portal ----------------------------------------------------------
    def open_portal(self, *, force: bool = False) -> None:
        """Open the operational consulta URL once per session."""

        if self._portal_opened and not force:
            return
        url = self.config.sat_consulta_url or self.config.sat_base_url
        self.browser_session.page.goto(url)
        self._portal_opened = True

    # -- search ----------------------------------------------------------
    def _wait_for_hs_input(self):
        deadline = self.monotonic() + max(self.config.action_timeout_ms, 0) / 1000.0
        while True:
            if self.is_query_enabled():
                return self.selectors().hs_code_input()
            if self.monotonic() >= deadline:
                break
            self.sleep(self.config.captcha_poll_interval_seconds)
        raise FormNotAvailableError(self._diagnose_missing_form())

    def _diagnose_missing_form(self) -> str:
        page = self.browser_session.page
        url = ""
        try:
            url = page.url
        except Exception:  # pragma: no cover - defensive
            url = "unknown"
        if self.is_captcha_active():
            reason = "CAPTCHA activo"
        elif not self.has_form():
            reason = "formulario frmBuscar ausente (¿landing o error del portal?)"
        else:
            reason = "el campo frmBuscar:txtCodigo no quedó visible/habilitado (¿selector obsoleto?)"
        return f"{reason}; URL actual: {url}"

    def _form_code_value(self) -> str:
        bundle = self.selectors()
        if not bundle.has_any(HS_CODE_INPUT_SELECTORS):
            return ""
        try:
            return bundle.hs_code_input().input_value() or ""
        except Exception:  # pragma: no cover - defensive
            return ""

    def _results_available(self) -> bool:
        bundle = self.selectors()
        return any(bundle.has_any(section_submit_selectors(label)) for label in SECTION_LABELS.values())

    def wait_for_search_results(self, entry: HsCodeEntry) -> None:
        """Wait for explicit DOM signals instead of ``networkidle``."""

        deadline = self.monotonic() + max(self.config.navigation_timeout_ms, 0) / 1000.0
        while True:
            if self.is_captcha_active():
                return
            if self._results_available() and self._matches_active_code(entry):
                return
            if self.monotonic() >= deadline:
                break
            self.sleep(self.config.captcha_poll_interval_seconds)
        raise FormNotAvailableError(
            f"Los resultados de {entry.normalized_code} no aparecieron; {self._diagnose_missing_form()}"
        )

    def _matches_active_code(self, entry: HsCodeEntry) -> bool:
        value = self._form_code_value()
        if not value:
            return True
        return _digits(value) == _digits(entry.normalized_code)

    def search_hs_code(self, entry: HsCodeEntry) -> None:
        # The CAPTCHA is always resolved before the HS field is located or filled.
        for attempt in range(2):
            self.ensure_captcha_cleared(entry.normalized_code)
            input_locator = self._wait_for_hs_input()
            input_locator.fill(entry.raw_code)
            self.selectors().search_button().click()
            if self.is_captcha_active() and attempt == 0:
                continue
            self.ensure_captcha_cleared(entry.normalized_code)
            self.wait_for_search_results(entry)
            return

    # -- evidence --------------------------------------------------------
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
        try:
            html = self._sanitize_html(page.content())
        except Exception:  # pragma: no cover - defensive
            html = ""
        (artifacts_dir / f"{stamp}.html").write_text(html, encoding="utf-8")
        diagnostics = {
            "code": code,
            "section": section,
            "error": str(error),
            "error_type": type(error).__name__,
            "url": self._safe_url(),
            "frames": self._frame_urls(),
            "captcha_active": self._safe_bool(self.is_captcha_active),
            "form_present": self._safe_bool(self.has_form),
            "hs_input_enabled": self._safe_bool(self.is_query_enabled),
        }
        (artifacts_dir / f"{stamp}.json").write_text(
            json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _safe_bool(probe: Callable[[], bool]) -> bool | None:
        try:
            return bool(probe())
        except Exception:  # pragma: no cover - defensive
            return None

    def _safe_url(self) -> str:
        try:
            return self.browser_session.page.url
        except Exception:  # pragma: no cover - defensive
            return "unknown"

    def _frame_urls(self) -> list[str]:
        try:
            return [getattr(frame, "url", "") for frame in (getattr(self.browser_session.page, "frames", []) or [])]
        except Exception:  # pragma: no cover - defensive
            return []

    # -- sections --------------------------------------------------------
    def _section_label(self, key: str) -> str:
        return SECTION_LABELS[key]

    def open_section_html(self, section: str) -> str:
        """Submit ``frmBuscar`` to a temporary tab, keeping the main tab valid.

        The legacy Selenium flow proved that a plain click is not enough: the
        validated form must stay on the main tab while the JSF submit is routed
        to a throwaway tab through ``form.target``.
        """

        label = self._section_label(section)
        context = self.form_context()
        self._section_counter += 1
        marker = f"sat-section-{self._section_counter}"
        target = f"satSection{self._section_counter}"
        prepared = context.evaluate(
            PREPARE_SECTION_SUBMIT_SCRIPT,
            {"formSelector": SAT_FORM_SELECTOR, "label": label, "marker": marker, "target": target},
        )
        if not prepared or not prepared.get("ok"):
            reason = (prepared or {}).get("reason", "unknown")
            raise SectionNavigationError(f"No se pudo preparar la sección '{label}': {reason}")
        previous_target = prepared.get("previousTarget", "")
        try:
            browser_context = self.browser_session.context
            with browser_context.expect_page() as page_info:
                context.evaluate(SUBMIT_FORM_SCRIPT, {"formSelector": SAT_FORM_SELECTOR})
            popup = page_info.value
            try:
                popup.wait_for_load_state("load")
                html = popup.content()
            finally:
                popup.close()
        finally:
            try:
                context.evaluate(
                    RESTORE_FORM_SCRIPT,
                    {"formSelector": SAT_FORM_SELECTOR, "marker": marker, "previousTarget": previous_target},
                )
            except Exception:  # pragma: no cover - defensive
                logger.debug("Could not restore frmBuscar after section '%s'", label)
        return html

    # -- orchestration ---------------------------------------------------
    def _handle_failure(self, code: str, section: str, exc: Exception) -> None:
        """Persist evidence and a resumable state for a failed step."""

        self.capture_evidence(code, section, exc)
        if isinstance(exc, (CaptchaRequiredError, CaptchaTimeoutError)):
            # CAPTCHA pauses are never permanent and never discard checkpoints.
            self.storage.update_state(code, ProcessingState.captcha_required, str(exc))
        else:
            self.storage.update_state(code, ProcessingState.retryable_error, str(exc))

    def process_code(self, entry: HsCodeEntry, *, force_restart: bool = False, position: str = "") -> None:
        row = self.storage.get_code(entry.normalized_code)
        if row is None:
            self.storage.upsert_code(entry.normalized_code, entry.raw_code, ProcessingState.pending)
            row = self.storage.get_code(entry.normalized_code)
        state_value = ProcessingState.pending.value if force_restart else row["state"]
        processed_sections = set() if force_restart else self.storage.get_processed_sections(entry.normalized_code)
        resume_point = build_resume_point(entry.normalized_code, state_value, processed_sections)
        if resume_point.next_section is None and not force_restart:
            if resume_point.state == ProcessingState.quotas_completed:
                # All four sections were already persisted in a previous run but
                # the process crashed before the final state transition. Finalize
                # instead of leaving the code stuck in quotas_completed forever.
                self.storage.update_state(entry.normalized_code, ProcessingState.completed)
            return

        self.announce(f"{position}HS {entry.normalized_code}".strip())
        self.storage.update_state(entry.normalized_code, ProcessingState.in_progress)
        self.storage.record_attempt(entry.normalized_code)
        self.announce("  Buscando código…")
        try:
            self.search_hs_code(entry)
        except Exception as exc:
            self._handle_failure(entry.normalized_code, "search", exc)
            raise

        started = False
        for section in SECTION_SEQUENCE:
            if not started and section != (resume_point.next_section or "rights"):
                continue
            started = True
            label = self._section_label(section)
            try:
                self.ensure_captcha_cleared(entry.normalized_code)
                html = self.open_section_html(section)
                result = SECTION_PARSERS[section](html)
                self.storage.save_section_rows(entry.normalized_code, section, result.rows, section_status=result.status)
                self.storage.update_state(entry.normalized_code, SECTION_PROGRESS[section])
                outcome = "sin cuotas" if getattr(result, "status", "") == "no_quotas" else "completado"
                self.announce(f"  {label}: {outcome}")
            except Exception as exc:
                self._handle_failure(entry.normalized_code, section, exc)
                raise
        self.storage.update_state(entry.normalized_code, ProcessingState.completed)
        self.announce("Checkpoint guardado.")

    def process_entries(self, entries: list[HsCodeEntry], *, force_restart: bool = False) -> None:
        self.open_portal()
        total = len(entries)
        failures: list[Exception] = []
        for index, entry in enumerate(entries, start=1):
            position = f"[{index}/{total}] "
            last_error: Exception | None = None
            for attempt in range(1, self.config.max_retries + 2):
                try:
                    self.process_code(entry, force_restart=force_restart, position=position)
                    last_error = None
                    break
                except CaptchaTimeoutError:
                    # Nobody solved the CAPTCHA: retrying is pointless and would
                    # only hammer the portal. Stop with a resumable state.
                    raise
                except Exception as exc:
                    last_error = exc
                    if attempt > self.config.max_retries:
                        break
                    self.sleep(self.config.retry_backoff_factor * attempt)
            if last_error is not None:
                logger.error("HS %s failed: %s", entry.normalized_code, last_error)
                failures.append(last_error)
            if self.config.delay_between_codes_seconds > 0:
                self.sleep(self.config.delay_between_codes_seconds)
        if failures:
            raise failures[0]


def run_navigation(entries: list[HsCodeEntry], config: AppConfig, storage: Storage, *, force_restart: bool = False) -> None:
    with BrowserSession(config) as browser_session:
        NavigationService(config=config, storage=storage, browser_session=browser_session).process_entries(entries, force_restart=force_restart)
