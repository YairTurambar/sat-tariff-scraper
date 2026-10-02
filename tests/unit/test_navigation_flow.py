"""Offline tests for the post-CAPTCHA automatic extraction flow.

Everything is exercised against local fakes: no browser, no network and no
CAPTCHA solving happen here.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from sat_tariff import captcha as captcha_module
from sat_tariff import navigation as navigation_module
from sat_tariff.captcha import CaptchaTimeoutError, wait_for_manual_captcha_resolution
from sat_tariff.config import AppConfig, load_config
from sat_tariff.models import HsCodeEntry, ProcessingState
from sat_tariff.navigation import NavigationService
from sat_tariff.selectors import (
    CAPTCHA_INPUT_SELECTORS,
    HS_CODE_INPUT_SELECTORS,
    SAT_FORM_SELECTOR,
    SEARCH_BUTTON_SELECTORS,
    SelectorBundle,
    find_form_context,
    section_submit_selectors,
)
from sat_tariff.storage import Storage

SECTION_HTML = "<html><body><table></table></body></html>"


class FakeElement:
    def __init__(self, *, visible=True, enabled=True, editable=True, value=""):
        self.visible = visible
        self.enabled = enabled
        self.editable = editable
        self.value = value


class FakeLocator:
    def __init__(self, page, selector, elements):
        self.page = page
        self.selector = selector
        self.elements = elements

    def count(self):
        return len(self.elements)

    @property
    def first(self):
        return self

    def _element(self):
        return self.elements[0]

    def is_visible(self):
        return self._element().visible

    def is_enabled(self):
        return self._element().enabled

    def is_editable(self):
        return self._element().editable

    def input_value(self):
        return self._element().value

    def fill(self, value):
        self.page.events.append(("fill", value))
        self._element().value = value

    def click(self):
        self.page.events.append(("click", self.selector))
        self.page.on_search_click()


class FakeFormContext:
    """A page or frame exposing the ``frmBuscar`` form."""

    def __init__(self, page):
        self.page = page

    def locator(self, selector):
        return FakeLocator(self.page, selector, self.page.elements_for(selector))

    def get_by_role(self, *args, **kwargs):  # pragma: no cover - defensive
        return FakeLocator(self.page, "role", [])

    def get_by_text(self, *args, **kwargs):  # pragma: no cover - defensive
        return FakeLocator(self.page, "text", [])

    def evaluate(self, script, arg=None):
        return self.page.evaluate(script, arg)


class FakePage:
    def __init__(self, *, url="https://farm2.sat.gob.gt/consulta.jsf", in_frame=False):
        self.url = url
        self.events: list[tuple] = []
        self.captcha_visible = False
        self.form_present = True
        self.sections_present = False
        self.hs_input = FakeElement()
        self.popups: list["FakePopup"] = []
        self.form_target = ""
        self.hidden_inputs: list[dict] = []
        self.on_search_click = lambda: self._default_search_click()
        self._frame = FakeFormContext(self) if in_frame else None
        self.frames = [self, self._frame] if in_frame else [self]
        self.in_frame = in_frame

    # -- fake DOM -----------------------------------------------------
    def _default_search_click(self):
        self.sections_present = True

    def elements_for(self, selector):
        if selector in CAPTCHA_INPUT_SELECTORS:
            return [FakeElement()] if self.captcha_visible else []
        if selector == SAT_FORM_SELECTOR:
            return [FakeElement()] if self.form_present else []
        if selector in HS_CODE_INPUT_SELECTORS:
            return [self.hs_input] if self.form_present else []
        if selector in SEARCH_BUTTON_SELECTORS:
            return [FakeElement()] if self.form_present else []
        if "value=" in selector:
            return [FakeElement()] if self.sections_present else []
        return []

    def locator(self, selector):
        if self.in_frame:
            return FakeLocator(self, selector, [])
        return FakeLocator(self, selector, self.elements_for(selector))

    def get_by_role(self, *args, **kwargs):  # pragma: no cover - defensive
        return FakeLocator(self, "role", [])

    def get_by_text(self, *args, **kwargs):  # pragma: no cover - defensive
        return FakeLocator(self, "text", [])

    def goto(self, url):
        self.events.append(("goto", url))
        self.url = url

    def screenshot(self, **kwargs):
        Path(kwargs["path"]).write_bytes(b"png")

    def content(self):
        return "<html><body><script>var token='abc';</script></body></html>"

    def evaluate(self, script, arg=None):
        arg = arg or {}
        if script is navigation_module.PREPARE_SECTION_SUBMIT_SCRIPT:
            if not self.sections_present:
                return {"ok": False, "reason": "section-button-not-found"}
            previous = self.form_target
            self.hidden_inputs.append({"name": "frmBuscar:j_id", "marker": arg["marker"]})
            self.form_target = arg["target"]
            return {"ok": True, "previousTarget": previous, "name": "frmBuscar:j_id", "value": arg["label"]}
        if script is navigation_module.SUBMIT_FORM_SCRIPT:
            self.events.append(("submit", self.form_target))
            self.popups.append(FakePopup(SECTION_HTML))
            return True
        if script is navigation_module.RESTORE_FORM_SCRIPT:
            self.form_target = arg.get("previousTarget", "")
            self.hidden_inputs = [item for item in self.hidden_inputs if item["marker"] != arg["marker"]]
            return True
        raise AssertionError(f"Unexpected script: {script}")  # pragma: no cover


class FakePopup:
    def __init__(self, html):
        self.html = html
        self.closed = False

    def wait_for_load_state(self, state):
        assert state == "load"

    def content(self):
        return self.html

    def close(self):
        self.closed = True


class FakeEventInfo:
    def __init__(self, page):
        self._page = page

    @property
    def value(self):
        return self._page


class FakeBrowserContext:
    def __init__(self, page):
        self.page = page

    @contextmanager
    def expect_page(self):
        info = FakeEventInfo(None)
        yield info
        info._page = self.page.popups.pop()


class FakeBrowserSession:
    def __init__(self, page):
        self.page = page
        self.context = FakeBrowserContext(page)


def make_config(tmp_path: Path, **overrides) -> AppConfig:
    config = AppConfig(
        persistent_profile_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
        logs_dir=tmp_path / "logs",
        sqlite_db=tmp_path / "db.sqlite3",
        output_xlsx=tmp_path / "out.xlsx",
        delay_between_codes_seconds=0.0,
        captcha_poll_interval_seconds=0.0,
        max_retries=0,
    )
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def make_service(tmp_path, page, **config_overrides):
    config = make_config(tmp_path, **config_overrides)
    storage = Storage(config.sqlite_db)
    storage.initialize()
    clock = {"now": 0.0}

    def monotonic():
        return clock["now"]

    def sleep(seconds):
        clock["now"] += max(seconds, 0.1)

    service = NavigationService(
        config=config,
        storage=storage,
        browser_session=FakeBrowserSession(page),
        announce=lambda message: page.events.append(("say", message)),
        sleep=sleep,
        monotonic=monotonic,
    )
    return service, storage


def entry(code: str) -> HsCodeEntry:
    return HsCodeEntry(raw_code=code, normalized_code=code)


def _stub_parsers(monkeypatch, status="ok"):
    class Result:
        rows: list = []
        status = ""

    def parser(html):
        result = Result()
        result.rows = []
        result.status = status
        return result

    monkeypatch.setattr(navigation_module, "SECTION_PARSERS", {key: parser for key in navigation_module.SECTION_SEQUENCE})


@pytest.fixture(autouse=True)
def forbid_input(monkeypatch):
    def _explode(*args, **kwargs):
        raise AssertionError("input() must not be called by default")

    monkeypatch.setattr("builtins.input", _explode)


# 1. input() is never used by default -------------------------------------
def test_captcha_wait_does_not_prompt_by_default():
    states = iter([True, True, False])
    calls = []
    wait_for_manual_captcha_resolution(
        lambda: next(states),
        lambda: True,
        timeout_seconds=10,
        poll_interval=0,
        sleep=lambda _: calls.append("poll"),
        monotonic=lambda: 0.0,
        announce=lambda message: None,
    )
    assert calls == ["poll"]


def test_optional_enter_fallback_is_opt_in():
    states = iter([True, True, False])
    prompts = []
    wait_for_manual_captcha_resolution(
        lambda: next(states),
        lambda: True,
        timeout_seconds=10,
        poll_interval=0,
        require_enter=True,
        prompt=lambda message: prompts.append(message) or "",
        sleep=lambda _: None,
        monotonic=lambda: 0.0,
        announce=lambda message: None,
    )
    assert prompts == [captcha_module.ENTER_PROMPT]
    assert len(prompts) == 1


# 2. CAPTCHA visible -> HS input enabled starts automatically --------------
def test_extraction_starts_automatically_once_input_is_enabled(tmp_path, monkeypatch):
    _stub_parsers(monkeypatch)
    page = FakePage()
    page.captcha_visible = True
    page.hs_input.enabled = False
    service, storage = make_service(tmp_path, page, captcha_timeout_seconds=30)

    original_sleep = service.sleep
    polls = {"count": 0}

    def sleep(seconds):
        polls["count"] += 1
        if polls["count"] >= 2:
            page.captcha_visible = False
            page.hs_input.enabled = True
        original_sleep(seconds)

    service.sleep = sleep
    service.process_entries([entry("0101210000")])

    assert storage.get_code("0101210000")["state"] == ProcessingState.completed.value
    messages = [value for kind, value in page.events if kind == "say"]
    assert captcha_module.RESOLVED_MESSAGE in messages
    storage.close()


# 3. search_hs_code waits for the CAPTCHA before touching the input -------
def test_search_waits_for_captcha_before_filling(tmp_path):
    page = FakePage()
    page.captcha_visible = True
    service, storage = make_service(tmp_path, page, captcha_timeout_seconds=30)
    storage.upsert_code("0101210000", "0101210000", ProcessingState.pending)

    original_sleep = service.sleep

    def sleep(seconds):
        page.captcha_visible = False
        original_sleep(seconds)

    service.sleep = sleep
    service.search_hs_code(entry("0101210000"))

    kinds = [kind for kind, _ in page.events]
    assert "fill" in kinds
    said_waiting = page.events.index(("say", captcha_module.WAITING_MESSAGE))
    filled = kinds.index("fill")
    assert said_waiting < filled
    storage.close()


# 4. Leading zeros are preserved -----------------------------------------
def test_leading_zeros_are_preserved(tmp_path):
    page = FakePage()
    service, storage = make_service(tmp_path, page)
    storage.upsert_code("0101210000", "0101210000", ProcessingState.pending)
    service.search_hs_code(entry("0101210000"))
    assert page.hs_input.value == "0101210000"
    storage.close()


# 5. The real submit button selector is used ------------------------------
def test_search_button_prefers_frm_buscar_pen():
    page = FakePage()
    bundle = SelectorBundle(page)
    assert bundle.search_button().selector == "#frmBuscar\\:pen"
    assert "input[name='frmBuscar:pen']" in SEARCH_BUTTON_SELECTORS
    assert "input[type='submit'][value='Buscar']" in SEARCH_BUTTON_SELECTORS
    assert "input[type='submit'][value='Consultar']" in SEARCH_BUTTON_SELECTORS


# 6. Sections open in a temporary tab and the main form is restored -------
def test_section_opens_temporary_tab_and_restores_form(tmp_path):
    page = FakePage()
    page.sections_present = True
    page.form_target = "_self"
    service, storage = make_service(tmp_path, page)

    html = service.open_section_html("rights")

    assert html == SECTION_HTML
    assert page.form_target == "_self"
    assert page.hidden_inputs == []
    assert any(kind == "submit" for kind, _ in page.events)
    submit_target = next(value for kind, value in page.events if kind == "submit")
    assert submit_target.startswith("satSection")
    storage.close()


# 7. Two codes processed after a single manual resolution -----------------
def test_two_codes_after_single_manual_resolution(tmp_path, monkeypatch):
    _stub_parsers(monkeypatch)
    page = FakePage()
    page.captcha_visible = True
    service, storage = make_service(tmp_path, page, captcha_timeout_seconds=30)

    original_sleep = service.sleep

    def sleep(seconds):
        page.captcha_visible = False
        original_sleep(seconds)

    service.sleep = sleep
    service.process_entries([entry("0101210000"), entry("0101290000")])

    assert storage.get_code("0101210000")["state"] == ProcessingState.completed.value
    assert storage.get_code("0101290000")["state"] == ProcessingState.completed.value
    waits = [value for kind, value in page.events if kind == "say" and value == captcha_module.WAITING_MESSAGE]
    assert len(waits) == 1
    storage.close()


# 8. A CAPTCHA reappearing on the second code pauses and continues --------
def test_captcha_reappearing_pauses_and_continues(tmp_path, monkeypatch):
    _stub_parsers(monkeypatch)
    page = FakePage()
    service, storage = make_service(tmp_path, page, captcha_timeout_seconds=30)
    seen: list[str] = []

    def on_click():
        page.sections_present = True
        if page.hs_input.value == "0101290000" and "0101290000" not in seen:
            seen.append("0101290000")
            page.captcha_visible = True

    page.on_search_click = on_click
    original_sleep = service.sleep

    def sleep(seconds):
        page.captcha_visible = False
        original_sleep(seconds)

    service.sleep = sleep
    service.process_entries([entry("0101210000"), entry("0101290000")])

    assert storage.get_code("0101210000")["state"] == ProcessingState.completed.value
    assert storage.get_code("0101290000")["state"] == ProcessingState.completed.value
    assert ("say", captcha_module.WAITING_MESSAGE) in page.events
    storage.close()


# 9. The form is found on the direct page and inside a frame --------------
def test_form_context_is_found_on_page_and_in_frame():
    direct = FakePage()
    assert find_form_context(direct) is direct

    landing = FakePage(in_frame=True)
    context = find_form_context(landing)
    assert context is landing.frames[1]
    assert context.locator(SAT_FORM_SELECTOR).count() == 1


# 10. Timeout produces evidence and a resumable state ---------------------
def test_captcha_timeout_writes_evidence_and_keeps_state_recoverable(tmp_path, monkeypatch):
    _stub_parsers(monkeypatch)
    page = FakePage()
    page.captcha_visible = True
    service, storage = make_service(tmp_path, page, captcha_timeout_seconds=1)

    with pytest.raises(CaptchaTimeoutError):
        service.process_entries([entry("0101210000")])

    row = storage.get_code("0101210000")
    assert row["state"] == ProcessingState.captcha_required.value
    artifacts = list(Path(service.config.artifacts_dir).glob("0101210000-*.json"))
    assert artifacts, "a diagnostic artifact must be written"
    html_files = list(Path(service.config.artifacts_dir).glob("0101210000-*.html"))
    assert html_files and "<script>" not in html_files[0].read_text(encoding="utf-8")
    storage.close()


# 11. The landing page is not reloaded between codes ----------------------
def test_portal_is_opened_once(tmp_path, monkeypatch):
    _stub_parsers(monkeypatch)
    page = FakePage()
    service, storage = make_service(tmp_path, page)
    service.process_entries([entry("0101210000"), entry("0101290000")])
    gotos = [value for kind, value in page.events if kind == "goto"]
    assert gotos == [service.config.sat_consulta_url]
    storage.close()


def test_consulta_url_defaults_to_direct_query(tmp_path, monkeypatch):
    monkeypatch.delenv("SAT_CONSULTA_URL", raising=False)
    config = load_config(tmp_path / "missing.env")
    assert config.sat_consulta_url == (
        "https://farm2.sat.gob.gt/saqbe-arancel-publico/aduana/arancel/consulta/consulta.jsf"
    )
    assert config.captcha_timeout_seconds == 300.0
    assert config.captcha_poll_interval_seconds == 1.0
    assert config.captcha_require_enter is False

    monkeypatch.setenv("SAT_CONSULTA_URL", "https://example.test/consulta.jsf")
    monkeypatch.setenv("SAT_CAPTCHA_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("SAT_CAPTCHA_POLL_INTERVAL_SECONDS", "0.5")
    monkeypatch.setenv("SAT_CAPTCHA_REQUIRE_ENTER", "true")
    config = load_config(tmp_path / "missing.env")
    assert config.sat_consulta_url == "https://example.test/consulta.jsf"
    assert config.captcha_timeout_seconds == 45.0
    assert config.captcha_poll_interval_seconds == 0.5
    assert config.captcha_require_enter is True


def test_section_submit_selectors_target_the_form():
    selectors = section_submit_selectors("Derechos e impuestos")
    assert selectors[0] == "form[name='frmBuscar'] input[type='submit'][value='Derechos e impuestos']"
