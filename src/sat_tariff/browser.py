"""Playwright browser wrapper."""

from __future__ import annotations

from dataclasses import dataclass

from .config import AppConfig


class BrowserUnavailableError(RuntimeError):
    """Raised when Playwright is unavailable for browser-backed commands."""


@dataclass(slots=True)
class BrowserSession:
    config: AppConfig
    playwright: object | None = None
    context: object | None = None
    page: object | None = None

    def start(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - exercised via CLI tests
            raise BrowserUnavailableError(
                "Playwright is not installed or could not be imported. Install with 'pip install -e .[dev]' and, outside this sandbox, run 'playwright install'."
            ) from exc

        self.config.ensure_directories()
        self.playwright = sync_playwright().start()
        browser_launcher = getattr(self.playwright, self.config.browser_type)
        self.context = browser_launcher.launch_persistent_context(
            user_data_dir=str(self.config.persistent_profile_dir),
            headless=self.config.headless,
        )
        self.context.set_default_navigation_timeout(self.config.navigation_timeout_ms)
        self.context.set_default_timeout(self.config.action_timeout_ms)
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.goto(self.config.sat_base_url)
        return self

    def close(self) -> None:
        if self.context is not None:
            self.context.close()
        if self.playwright is not None:
            self.playwright.stop()

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False
