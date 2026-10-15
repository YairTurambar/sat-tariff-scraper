"""Offline tests for ``run-batches`` / ``resume-batches``.

A fake Playwright page and a fake ``BrowserSession`` are used: Chrome is never
launched, the SAT portal is never contacted and no CAPTCHA is ever solved
automatically.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sat_tariff import captcha as captcha_module
from sat_tariff import cli
from sat_tariff import navigation as navigation_module
from sat_tariff.batches import prepare_batches
from sat_tariff.config import AppConfig
from sat_tariff.models import ProcessingState
from sat_tariff.navigation import NavigationService, run_navigation_batches
from sat_tariff.storage import Storage

from test_navigation_flow import FakeBrowserSession, FakePage, _stub_parsers, make_config


class SessionRecorder:
    """Fake ``BrowserSession`` context manager counting enter/exit calls."""

    def __init__(self, page):
        self.page = page
        self.enter_count = 0
        self.exit_count = 0
        self.session = FakeBrowserSession(page)

    def factory(self, config):
        recorder = self

        class _Session:
            def __enter__(self_inner):
                recorder.enter_count += 1
                return recorder.session

            def __exit__(self_inner, *exc_info):
                recorder.exit_count += 1
                return False

        return _Session()


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    _stub_parsers(monkeypatch)
    page = FakePage()
    recorder = SessionRecorder(page)
    monkeypatch.setattr(navigation_module, "BrowserSession", recorder.factory)
    services: list[NavigationService] = []
    original_service = navigation_module.NavigationService

    def tracking_service(**kwargs):
        service = original_service(**kwargs)
        service.sleep = lambda seconds: None
        service.announce = lambda message: page.events.append(("say", message))
        services.append(service)
        return service

    monkeypatch.setattr(navigation_module, "NavigationService", tracking_service)
    return page, recorder, services


def write_master(tmp_path: Path, total: int) -> Path:
    master = tmp_path / "HS_codes.txt"
    master.write_text("".join(f"{index:010d}\n" for index in range(total)), encoding="utf-8")
    return master


def batch_config(tmp_path: Path, total: int, batch_size: int) -> AppConfig:
    config = make_config(tmp_path)
    config.input_file = write_master(tmp_path, total)
    config.batch_directory = tmp_path / "batches"
    config.batch_size = batch_size
    prepare_batches(config)
    return config


def prepare_cli_env(monkeypatch, config: AppConfig) -> None:
    monkeypatch.setenv("SAT_INPUT_FILE", str(config.input_file))
    monkeypatch.setenv("SAT_BATCH_DIRECTORY", str(config.batch_directory))
    monkeypatch.setenv("SAT_BATCH_SIZE", str(config.batch_size))
    monkeypatch.setenv("SAT_SQLITE_DB", str(config.sqlite_db))
    monkeypatch.setenv("SAT_ARTIFACTS_DIR", str(config.artifacts_dir))
    monkeypatch.setenv("SAT_LOGS_DIR", str(config.logs_dir))
    monkeypatch.setenv("SAT_PROFILE_DIR", str(config.persistent_profile_dir))
    monkeypatch.setenv("SAT_OUTPUT_XLSX", str(config.output_xlsx))
    monkeypatch.setenv("SAT_DELAY_BETWEEN_CODES_SECONDS", "0")
    monkeypatch.setenv("SAT_CAPTCHA_POLL_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("SAT_MAX_RETRIES", "0")


# 14-17. one session, one service, one page.goto() ------------------------
def test_run_batches_uses_a_single_browser_session(tmp_path, monkeypatch, capsys, fake_env):
    page, recorder, services = fake_env
    config = batch_config(tmp_path, total=6, batch_size=2)
    prepare_cli_env(monkeypatch, config)

    assert cli.main(["run-batches"]) == 0

    assert recorder.enter_count == 1
    assert recorder.exit_count == 1
    assert len(services) == 1
    assert len([event for event in page.events if event[0] == "goto"]) == 1

    out = capsys.readouterr().out
    assert "Processed 6 HS codes." in out
    assert "Lotes recorridos: 3" in out
    announced = [message for kind, message in page.events if kind == "say"]
    assert "Lote 1/3 — 2 códigos" in announced
    assert "Lote 3/3 — 2 códigos" in announced

    storage = Storage(config.sqlite_db)
    try:
        states = storage.get_states(f"{index:010d}" for index in range(6))
        assert set(states.values()) == {ProcessingState.completed.value}
    finally:
        storage.close()


# 25. global and per-batch progress ---------------------------------------
def test_progress_is_global_and_per_batch(tmp_path, monkeypatch, fake_env):
    page, _recorder, _services = fake_env
    config = batch_config(tmp_path, total=4, batch_size=2)
    prepare_cli_env(monkeypatch, config)

    assert cli.main(["run-batches"]) == 0

    messages = [message for kind, message in page.events if kind == "say"]
    assert "Lote 1/2 — 2 códigos" in messages
    assert "Lote 2/2 — 2 códigos" in messages
    assert "[global 1/4 | lote 1/2] HS 0000000000" in messages
    assert "[global 3/4 | lote 1/2] HS 0000000002" in messages
    assert "[global 4/4 | lote 2/2] HS 0000000003" in messages


# 18 & 19. CAPTCHA solved once, and reappearing later ---------------------
def test_captcha_solved_once_covers_every_batch(tmp_path, monkeypatch, fake_env):
    page, recorder, _services = fake_env
    page.captcha_visible = True
    page.hs_input.enabled = False
    config = batch_config(tmp_path, total=4, batch_size=2)
    prepare_cli_env(monkeypatch, config)
    monkeypatch.setenv("SAT_CAPTCHA_TIMEOUT_SECONDS", "30")

    waits = {"count": 0}

    def fake_wait(is_active, is_ready, **kwargs):
        waits["count"] += 1
        page.captcha_visible = False
        page.hs_input.enabled = True
        kwargs["announce"](captcha_module.RESOLVED_MESSAGE)

    monkeypatch.setattr(navigation_module, "wait_for_manual_captcha_resolution", fake_wait)

    assert cli.main(["run-batches"]) == 0
    assert waits["count"] == 1
    assert recorder.enter_count == 1
    assert len([event for event in page.events if event[0] == "goto"]) == 1


def test_captcha_reappearing_in_a_later_batch_pauses_without_restarting(tmp_path, monkeypatch, fake_env):
    page, recorder, _services = fake_env
    config = batch_config(tmp_path, total=4, batch_size=2)
    prepare_cli_env(monkeypatch, config)
    monkeypatch.setenv("SAT_CAPTCHA_TIMEOUT_SECONDS", "30")

    waits = {"count": 0}

    def fake_wait(is_active, is_ready, **kwargs):
        waits["count"] += 1
        page.captcha_visible = False
        kwargs["announce"](captcha_module.RESOLVED_MESSAGE)

    monkeypatch.setattr(navigation_module, "wait_for_manual_captcha_resolution", fake_wait)

    seen = {"count": 0}

    def on_search_click():
        seen["count"] += 1
        page.sections_present = True
        if seen["count"] == 3:  # third code: first of the second batch
            page.captcha_visible = True

    page.on_search_click = on_search_click

    assert cli.main(["run-batches"]) == 0
    assert waits["count"] >= 1
    assert recorder.enter_count == 1
    assert recorder.exit_count == 1
    assert len([event for event in page.events if event[0] == "goto"]) == 1


# 20 & 21. completed codes skipped, missing codes processed ---------------
def test_completed_codes_are_not_reextracted_and_missing_codes_are(tmp_path, monkeypatch, capsys, fake_env):
    page, recorder, _services = fake_env
    config = batch_config(tmp_path, total=4, batch_size=2)
    prepare_cli_env(monkeypatch, config)

    storage = Storage(config.sqlite_db)
    try:
        storage.upsert_code("0000000000", "0000000000", ProcessingState.completed)
        storage.save_section_rows("0000000000", "rights", [], section_status="ok")
    finally:
        storage.close()

    assert cli.main(["run-batches"]) == 0

    out = capsys.readouterr().out
    assert "Completados previamente: 1" in out
    assert "Processed 3 HS codes." in out
    announced = [message for kind, message in page.events if kind == "say" and "HS " in message]
    assert all("HS 0000000000" not in message for message in announced)
    assert any("HS 0000000003" in message for message in announced)
    assert recorder.enter_count == 1


# 22. resume-batches crosses batch boundaries keeping global order --------
def test_resume_batches_crosses_batch_boundaries(tmp_path, monkeypatch, fake_env):
    page, recorder, _services = fake_env
    config = batch_config(tmp_path, total=6, batch_size=2)
    prepare_cli_env(monkeypatch, config)

    storage = Storage(config.sqlite_db)
    try:
        for code in ("0000000000", "0000000002", "0000000004"):
            storage.upsert_code(code, code, ProcessingState.completed)
    finally:
        storage.close()

    assert cli.main(["resume-batches"]) == 0

    processed = [
        message.split("HS ")[1]
        for kind, message in page.events
        if kind == "say" and "HS " in message
    ]
    assert processed == ["0000000001", "0000000003", "0000000005"]
    assert recorder.enter_count == 1
    assert len([event for event in page.events if event[0] == "goto"]) == 1


def test_resume_batches_processes_manifest_codes_missing_from_sqlite(tmp_path, monkeypatch, fake_env):
    page, _recorder, _services = fake_env
    config = batch_config(tmp_path, total=4, batch_size=2)
    prepare_cli_env(monkeypatch, config)

    storage = Storage(config.sqlite_db)
    try:
        # Only one code exists in SQLite; the other three are manifest-only.
        storage.upsert_code("0000000001", "0000000001", ProcessingState.rights_completed)
    finally:
        storage.close()

    assert cli.main(["resume-batches"]) == 0

    processed = [
        message.split("HS ")[1]
        for kind, message in page.events
        if kind == "say" and "HS " in message
    ]
    assert processed == ["0000000000", "0000000001", "0000000002", "0000000003"]


# 23. nothing pending -> no browser ---------------------------------------
def test_no_pending_codes_does_not_open_the_browser(tmp_path, monkeypatch, capsys, fake_env):
    _page, recorder, _services = fake_env
    config = batch_config(tmp_path, total=2, batch_size=1)
    prepare_cli_env(monkeypatch, config)

    storage = Storage(config.sqlite_db)
    try:
        for code in ("0000000000", "0000000001"):
            storage.upsert_code(code, code, ProcessingState.completed)
    finally:
        storage.close()

    assert cli.main(["run-batches"]) == 0
    out = capsys.readouterr().out
    assert "Processed 0 HS codes." in out
    assert recorder.enter_count == 0


# 24. an interruption keeps checkpoints and resumes at the right section ---
def test_interruption_keeps_checkpoints_and_resumes_at_the_right_section(tmp_path, monkeypatch, fake_env):
    page, _recorder, _services = fake_env
    config = batch_config(tmp_path, total=4, batch_size=2)
    prepare_cli_env(monkeypatch, config)

    storage = Storage(config.sqlite_db)
    try:
        storage.upsert_code("0000000002", "0000000002", ProcessingState.rights_completed)
        storage.save_section_rows("0000000002", "rights", [{"agreement_name": "DAI"}], section_status="ok")
    finally:
        storage.close()

    opened: list[str] = []
    original = NavigationService.open_section_html

    def tracking_open(self, section):
        opened.append(f"{section}")
        return original(self, section)

    monkeypatch.setattr(NavigationService, "open_section_html", tracking_open, raising=False)

    assert cli.main(["resume-batches"]) == 0

    storage = Storage(config.sqlite_db)
    try:
        rows = storage.get_section_rows_by_code("rights")
        # The previously stored rights rows were not deleted nor reextracted.
        assert rows["0000000002"] == [{"agreement_name": "DAI"}]
        assert storage.get_code("0000000002")["state"] == ProcessingState.completed.value
    finally:
        storage.close()
    assert opened.count("rights") == 3


# Manifest guards stop before the browser is opened -----------------------
def test_stale_master_file_fails_before_opening_the_browser(tmp_path, monkeypatch, capsys, fake_env):
    _page, recorder, _services = fake_env
    config = batch_config(tmp_path, total=4, batch_size=2)
    prepare_cli_env(monkeypatch, config)
    config.input_file.write_text("0101210000\n", encoding="utf-8")

    assert cli.main(["run-batches"]) == 1
    err = capsys.readouterr().err
    assert "prepare-batches" in err
    assert recorder.enter_count == 0


def test_missing_batch_file_fails_before_opening_the_browser(tmp_path, monkeypatch, capsys, fake_env):
    _page, recorder, _services = fake_env
    config = batch_config(tmp_path, total=4, batch_size=2)
    prepare_cli_env(monkeypatch, config)
    (config.batch_directory / "HS_codes_002.txt").unlink()

    assert cli.main(["run-batches"]) == 1
    err = capsys.readouterr().err
    assert "HS_codes_002.txt" in err
    assert recorder.enter_count == 0


def test_run_batches_accepts_an_explicit_directory(tmp_path, monkeypatch, capsys, fake_env):
    _page, recorder, _services = fake_env
    config = batch_config(tmp_path, total=2, batch_size=1)
    prepare_cli_env(monkeypatch, config)
    monkeypatch.setenv("SAT_BATCH_DIRECTORY", str(tmp_path / "otro-directorio"))

    assert cli.main(["run-batches", "--directory", str(config.batch_directory)]) == 0

    assert "Processed 2 HS codes." in capsys.readouterr().out
    assert recorder.enter_count == 1


def test_run_navigation_batches_reuses_one_service(tmp_path, monkeypatch, fake_env):
    page, recorder, services = fake_env
    config = batch_config(tmp_path, total=4, batch_size=2)
    storage = Storage(config.sqlite_db)
    try:
        from sat_tariff.batches import build_batch_plans, load_batch_entries, load_manifest

        manifest = load_manifest(config.batch_directory)
        loaded = load_batch_entries(manifest)
        plans = build_batch_plans(loaded, {f"{index:010d}" for index in range(4)})
        run_navigation_batches(plans, config, storage, force_restart=False)
    finally:
        storage.close()

    assert len(plans) == 2
    assert len(services) == 1
    assert recorder.enter_count == 1
    assert recorder.exit_count == 1
    assert len([event for event in page.events if event[0] == "goto"]) == 1
