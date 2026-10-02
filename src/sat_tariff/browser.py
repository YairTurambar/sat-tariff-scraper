"""Playwright browser wrapper with system-browser fallback.

The Playwright-managed Chromium download is optional: when the managed binary
is missing (for example because the CDN is blocked or times out), the session
falls back to a Chromium-compatible browser already installed on the system.
Nothing is downloaded at run time.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import logging

from . import browser_discovery
from .config import AppConfig

logger = logging.getLogger("sat_tariff.browser")

NO_USABLE_BROWSER_MESSAGE = (
    "No usable browser was found.\n"
    "Set SAT_BROWSER_CHANNEL=chrome, set SAT_BROWSER_EXECUTABLE_PATH=..., or install a system "
    "Chrome/Edge/Chromium browser.\n"
    "The Playwright-managed Chromium download is optional when a system browser is available."
)

MISSING_EXECUTABLE_HINTS = (
    "executable doesn't exist",
    "executable does not exist",
    "looks like playwright",
    "playwright install",
    "no such file or directory",
)


class BrowserUnavailableError(RuntimeError):
    """Raised when no browser could be launched for browser-backed commands."""


class BrowserConfigurationError(BrowserUnavailableError):
    """Raised when explicit browser configuration is invalid."""


@dataclass(frozen=True, slots=True)
class LaunchStrategy:
    """A single, explicit attempt to launch a browser."""

    kind: str
    description: str
    channel: str | None = None
    executable_path: str | None = None

    def launch_options(self) -> dict[str, object]:
        options: dict[str, object] = {}
        if self.channel:
            options["channel"] = self.channel
        if self.executable_path:
            options["executable_path"] = self.executable_path
        return options


def build_launch_strategies(
    config: AppConfig,
    *,
    managed_browser: str | None = None,
    system_browsers: Sequence[str] | None = None,
) -> list[LaunchStrategy]:
    """Return the ordered launch strategies for the given configuration.

    Precedence:

    1. ``SAT_BROWSER_EXECUTABLE_PATH`` when configured (an explicit path that
       does not exist is a configuration error, never a silent fallback);
    2. ``SAT_BROWSER_CHANNEL`` when configured;
    3. the Playwright-managed binary, only when it is already installed;
    4. a system browser discovered automatically, when the fallback is enabled.

    The managed binary is only attempted when it is present on disk, so ``run``
    never triggers a browser download. Callers that already performed the
    discovery (such as ``doctor``) can pass the results to avoid rescanning.
    """

    if config.browser_executable_path:
        path = Path(config.browser_executable_path)
        if not path.is_file():
            raise BrowserConfigurationError(
                f"SAT_BROWSER_EXECUTABLE_PATH points to '{config.browser_executable_path}', "
                "which is not an existing file. Fix the path, use SAT_BROWSER_CHANNEL=chrome "
                "or msedge, or unset the variable to auto-detect a system browser."
            )
        return [
            LaunchStrategy(
                kind="executable_path",
                description=f"configured executable path ({path})",
                executable_path=str(path),
            )
        ]

    if config.browser_channel:
        return [
            LaunchStrategy(
                kind="channel",
                description=f"configured channel '{config.browser_channel}'",
                channel=config.browser_channel,
            )
        ]

    strategies: list[LaunchStrategy] = []
    managed = managed_browser if managed_browser is not None else browser_discovery.find_managed_chromium()
    if managed:
        strategies.append(
            LaunchStrategy(kind="managed", description="Playwright-managed browser")
        )
    if config.browser_fallback_to_system:
        candidates = (
            system_browsers
            if system_browsers is not None
            else browser_discovery.discover_system_browsers(extra_candidates=config.browser_candidate_paths)
        )
        for candidate in candidates:
            strategies.append(
                LaunchStrategy(
                    kind="system",
                    description=f"system browser ({candidate})",
                    executable_path=candidate,
                )
            )
    return strategies


def _is_missing_executable_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(hint in message for hint in MISSING_EXECUTABLE_HINTS)


@dataclass(slots=True)
class BrowserSession:
    config: AppConfig
    playwright: object | None = None
    context: object | None = None
    page: object | None = None
    strategy: LaunchStrategy | None = None

    def start(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - exercised via CLI tests
            raise BrowserUnavailableError(
                "Playwright is not installed or could not be imported. Install with 'pip install -e .[dev]'."
            ) from exc

        self.config.ensure_directories()
        strategies = build_launch_strategies(self.config)
        if not strategies:
            raise BrowserUnavailableError(NO_USABLE_BROWSER_MESSAGE)

        self.playwright = sync_playwright().start()
        failures: list[str] = []
        try:
            browser_launcher = getattr(self.playwright, self.config.browser_type)
            for strategy in strategies:
                try:
                    self.context = browser_launcher.launch_persistent_context(
                        user_data_dir=str(self.config.persistent_profile_dir),
                        headless=self.config.headless,
                        **strategy.launch_options(),
                    )
                except Exception as exc:
                    reason = "missing browser executable" if _is_missing_executable_error(exc) else type(exc).__name__
                    logger.warning("Browser launch failed using %s: %s", strategy.description, reason)
                    failures.append(f"{strategy.description}: {exc}")
                    continue
                self.strategy = strategy
                logger.info("Launched %s using %s", self.config.browser_type, strategy.description)
                break
            else:
                raise BrowserUnavailableError(
                    NO_USABLE_BROWSER_MESSAGE + "\nAttempts:\n" + "\n".join(f"- {item}" for item in failures)
                )
            self.context.set_default_navigation_timeout(self.config.navigation_timeout_ms)
            self.context.set_default_timeout(self.config.action_timeout_ms)
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        except Exception:
            self.close()
            raise
        return self

    def close(self) -> None:
        try:
            if self.context is not None:
                try:
                    self.context.close()
                except Exception:
                    logger.warning("Browser context could not be closed cleanly", exc_info=True)
                finally:
                    self.context = None
                    self.page = None
        finally:
            if self.playwright is not None:
                try:
                    self.playwright.stop()
                finally:
                    self.playwright = None

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False
