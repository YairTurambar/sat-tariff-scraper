from pathlib import Path

import pytest

from sat_tariff import browser_discovery as discovery_module
from sat_tariff.browser import (
    NO_USABLE_BROWSER_MESSAGE,
    BrowserConfigurationError,
    BrowserSession,
    BrowserUnavailableError,
    build_launch_strategies,
)
from sat_tariff.browser_discovery import discover_system_browsers, find_managed_chromium
from sat_tariff.config import AppConfig, load_config


def make_config(tmp_path: Path, **overrides) -> AppConfig:
    config = AppConfig(
        persistent_profile_dir=tmp_path / "profile",
        artifacts_dir=tmp_path / "artifacts",
        logs_dir=tmp_path / "logs",
        sqlite_db=tmp_path / "db.sqlite3",
        output_xlsx=tmp_path / "out.xlsx",
    )
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def test_browser_env_variables_are_parsed(monkeypatch, tmp_path):
    monkeypatch.setenv("SAT_BROWSER_CHANNEL", " msedge ")
    monkeypatch.setenv("SAT_BROWSER_EXECUTABLE_PATH", " /opt/chrome ")
    monkeypatch.setenv("SAT_BROWSER_FALLBACK_TO_SYSTEM", "false")
    monkeypatch.setenv("SAT_BROWSER_CANDIDATE_PATHS", "/one,/two")
    config = load_config(tmp_path / "missing.env")
    assert config.browser_channel == "msedge"
    assert config.browser_executable_path == "/opt/chrome"
    assert config.browser_fallback_to_system is False
    assert config.browser_candidate_paths == ("/one", "/two")


def test_defaults_enable_system_fallback(tmp_path):
    config = load_config(tmp_path / "missing.env")
    assert config.browser_channel == ""
    assert config.browser_executable_path == ""
    assert config.browser_fallback_to_system is True


def test_explicit_executable_path_wins(monkeypatch, tmp_path):
    executable = tmp_path / "chrome"
    executable.write_text("binary", encoding="utf-8")
    monkeypatch.setattr(discovery_module, "find_managed_chromium", lambda **_: "/managed/chrome")
    monkeypatch.setattr(discovery_module, "discover_system_browsers", lambda **_: ["/usr/bin/chromium"])
    config = make_config(tmp_path, browser_executable_path=str(executable), browser_channel="chrome")
    strategies = build_launch_strategies(config)
    assert [item.kind for item in strategies] == ["executable_path"]
    assert strategies[0].launch_options() == {"executable_path": str(executable)}


def test_missing_explicit_executable_path_is_actionable(tmp_path):
    config = make_config(tmp_path, browser_executable_path=str(tmp_path / "nope"))
    with pytest.raises(BrowserConfigurationError) as excinfo:
        build_launch_strategies(config)
    message = str(excinfo.value)
    assert "SAT_BROWSER_EXECUTABLE_PATH" in message
    assert "SAT_BROWSER_CHANNEL" in message


def test_channel_wins_over_managed_and_system(monkeypatch, tmp_path):
    monkeypatch.setattr(discovery_module, "find_managed_chromium", lambda **_: "/managed/chrome")
    monkeypatch.setattr(discovery_module, "discover_system_browsers", lambda **_: ["/usr/bin/chromium"])
    config = make_config(tmp_path, browser_channel="chrome")
    strategies = build_launch_strategies(config)
    assert [item.kind for item in strategies] == ["channel"]
    assert strategies[0].launch_options() == {"channel": "chrome"}


def test_managed_binary_precedes_system_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(discovery_module, "find_managed_chromium", lambda **_: "/managed/chrome")
    monkeypatch.setattr(discovery_module, "discover_system_browsers", lambda **_: ["/usr/bin/chromium"])
    strategies = build_launch_strategies(make_config(tmp_path))
    assert [item.kind for item in strategies] == ["managed", "system"]
    assert strategies[0].launch_options() == {}


def test_system_browsers_used_when_managed_binary_is_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(discovery_module, "find_managed_chromium", lambda **_: None)
    monkeypatch.setattr(discovery_module, "discover_system_browsers", lambda **_: ["/usr/bin/chromium"])
    strategies = build_launch_strategies(make_config(tmp_path))
    assert [item.kind for item in strategies] == ["system"]


def test_no_strategies_when_fallback_disabled_and_no_managed_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(discovery_module, "find_managed_chromium", lambda **_: None)
    monkeypatch.setattr(discovery_module, "discover_system_browsers", lambda **_: ["/usr/bin/chromium"])
    config = make_config(tmp_path, browser_fallback_to_system=False)
    assert build_launch_strategies(config) == []


def test_discovery_on_windows_uses_program_files(tmp_path):
    base = tmp_path / "Program Files"
    chrome = base / "Google" / "Chrome" / "Application" / "chrome.exe"
    chrome.parent.mkdir(parents=True)
    chrome.write_text("binary", encoding="utf-8")
    found = discover_system_browsers(
        platform_name="win32",
        environ={"PROGRAMFILES": str(base)},
        which=lambda name: None,
    )
    assert found == [str(chrome)]


def test_discovery_on_macos_uses_applications():
    existing = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    found = discover_system_browsers(
        platform_name="darwin",
        environ={},
        which=lambda name: None,
        is_file=lambda path: str(path) == existing,
    )
    assert found == [existing]


def test_discovery_on_linux_uses_path_lookup():
    found = discover_system_browsers(
        platform_name="linux",
        environ={},
        which=lambda name: "/usr/local/bin/chromium" if name == "chromium" else None,
        is_file=lambda path: str(path) == "/usr/local/bin/chromium",
    )
    assert found == ["/usr/local/bin/chromium"]


def test_discovery_prefers_extra_candidates_and_deduplicates():
    found = discover_system_browsers(
        platform_name="linux",
        environ={},
        which=lambda name: "/usr/bin/chromium" if name == "chromium" else None,
        is_file=lambda path: str(path) in {"/custom/chrome", "/usr/bin/chromium"},
        extra_candidates=("/custom/chrome", "/missing/chrome"),
    )
    assert found == ["/custom/chrome", "/usr/bin/chromium"]


def test_find_managed_chromium_detects_installed_binary(tmp_path):
    executable = tmp_path / "ms-playwright" / "chromium-1148" / "chrome-linux" / "chrome"
    executable.parent.mkdir(parents=True)
    executable.write_text("binary", encoding="utf-8")
    found = find_managed_chromium(
        platform_name="linux",
        environ={"PLAYWRIGHT_BROWSERS_PATH": str(tmp_path / "ms-playwright")},
    )
    assert found == str(executable)


def test_find_managed_chromium_prefers_newest_revision(tmp_path):
    registry = tmp_path / "ms-playwright"
    for revision in ("chromium-1099", "chromium-1148", "chromium_headless_shell-1148"):
        executable = registry / revision / "chrome-linux" / "chrome"
        executable.parent.mkdir(parents=True)
        executable.write_text("binary", encoding="utf-8")
    found = find_managed_chromium(
        platform_name="linux",
        environ={"PLAYWRIGHT_BROWSERS_PATH": str(registry)},
    )
    assert found == str(registry / "chromium-1148" / "chrome-linux" / "chrome")


def test_find_managed_chromium_returns_none_when_absent(tmp_path):
    found = find_managed_chromium(
        platform_name="linux",
        environ={"HOME": str(tmp_path)},
    )
    assert found is None


class FakeContext:
    def __init__(self):
        self.pages = []
        self.closed = False
        self.navigation_timeout = None
        self.timeout = None
        self.page = FakePage()

    def set_default_navigation_timeout(self, value):
        self.navigation_timeout = value

    def set_default_timeout(self, value):
        self.timeout = value

    def new_page(self):
        return self.page

    def close(self):
        self.closed = True


class FakePage:
    def __init__(self):
        self.goto_calls = []

    def goto(self, url):
        self.goto_calls.append(url)


class FakeLauncher:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def launch_persistent_context(self, **kwargs):
        self.calls.append(kwargs)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakePlaywright:
    def __init__(self, launcher):
        self.chromium = launcher
        self.stopped = False

    def stop(self):
        self.stopped = True


def install_fake_playwright(monkeypatch, launcher) -> FakePlaywright:
    instance = FakePlaywright(launcher)

    class FakeSyncPlaywright:
        def start(self):
            return instance

    import sys
    import types

    module = types.ModuleType("playwright")
    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.sync_playwright = lambda: FakeSyncPlaywright()
    module.sync_api = sync_api
    monkeypatch.setitem(sys.modules, "playwright", module)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)
    return instance


def test_start_falls_back_after_missing_managed_executable(monkeypatch, tmp_path):
    context = FakeContext()
    launcher = FakeLauncher(
        [
            Exception("Executable doesn't exist at /root/.cache/ms-playwright/chromium-1148/chrome-linux/chrome"),
            context,
        ]
    )
    instance = install_fake_playwright(monkeypatch, launcher)
    monkeypatch.setattr(discovery_module, "find_managed_chromium", lambda **_: "/managed/chrome")
    monkeypatch.setattr(discovery_module, "discover_system_browsers", lambda **_: ["/usr/bin/google-chrome"])

    session = BrowserSession(config=make_config(tmp_path)).start()

    assert session.strategy.kind == "system"
    assert launcher.calls[0].get("executable_path") is None
    assert launcher.calls[1]["executable_path"] == "/usr/bin/google-chrome"
    assert launcher.calls[1]["headless"] is False
    assert session.page is context.page
    assert context.page.goto_calls == []
    assert instance.stopped is False


def test_start_cleans_up_when_every_strategy_fails(monkeypatch, tmp_path):
    launcher = FakeLauncher([Exception("Executable doesn't exist at /managed/chrome")])
    instance = install_fake_playwright(monkeypatch, launcher)
    monkeypatch.setattr(discovery_module, "find_managed_chromium", lambda **_: "/managed/chrome")
    monkeypatch.setattr(discovery_module, "discover_system_browsers", lambda **_: [])

    with pytest.raises(BrowserUnavailableError) as excinfo:
        BrowserSession(config=make_config(tmp_path)).start()

    assert "No usable browser was found." in str(excinfo.value)
    assert instance.stopped is True


def test_start_without_strategies_does_not_start_playwright(monkeypatch, tmp_path):
    launcher = FakeLauncher([])
    instance = install_fake_playwright(monkeypatch, launcher)
    monkeypatch.setattr(discovery_module, "find_managed_chromium", lambda **_: None)
    monkeypatch.setattr(discovery_module, "discover_system_browsers", lambda **_: [])

    with pytest.raises(BrowserUnavailableError) as excinfo:
        BrowserSession(config=make_config(tmp_path)).start()

    assert str(excinfo.value) == NO_USABLE_BROWSER_MESSAGE
    assert instance.stopped is False
    assert launcher.calls == []


def test_close_stops_playwright_even_if_context_close_fails(monkeypatch, tmp_path):
    class FailingContext(FakeContext):
        def close(self):
            raise RuntimeError("context already gone")

    context = FailingContext()
    launcher = FakeLauncher([context])
    instance = install_fake_playwright(monkeypatch, launcher)
    monkeypatch.setattr(discovery_module, "find_managed_chromium", lambda **_: None)
    monkeypatch.setattr(discovery_module, "discover_system_browsers", lambda **_: ["/usr/bin/chromium"])

    session = BrowserSession(config=make_config(tmp_path)).start()
    session.close()

    assert instance.stopped is True
    assert session.context is None
