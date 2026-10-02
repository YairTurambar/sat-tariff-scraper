"""Offline discovery of Chromium-compatible browsers.

The helpers in this module never download anything and never execute the
browsers they find. They only inspect well-known locations and ``PATH``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
import os
import shutil
import sys

COMMAND_NAMES: tuple[str, ...] = (
    "google-chrome",
    "google-chrome-stable",
    "google-chrome-beta",
    "chrome",
    "chromium",
    "chromium-browser",
    "microsoft-edge",
    "microsoft-edge-stable",
    "msedge",
)

WINDOWS_RELATIVE_PATHS: tuple[str, ...] = (
    "Google\\Chrome\\Application\\chrome.exe",
    "Google\\Chrome Beta\\Application\\chrome.exe",
    "Google\\Chrome Dev\\Application\\chrome.exe",
    "Chromium\\Application\\chrome.exe",
    "Microsoft\\Edge\\Application\\msedge.exe",
    "Microsoft\\Edge Beta\\Application\\msedge.exe",
)

WINDOWS_BASE_ENV_VARS: tuple[str, ...] = (
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "LOCALAPPDATA",
)

MACOS_PATHS: tuple[str, ...] = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)

LINUX_PATHS: tuple[str, ...] = (
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/opt/google/chrome/chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
    "/usr/bin/microsoft-edge",
    "/usr/bin/microsoft-edge-stable",
    "/opt/microsoft/msedge/msedge",
)

MANAGED_RELATIVE_EXECUTABLES: dict[str, tuple[str, ...]] = {
    "win32": ("chrome-win\\chrome.exe",),
    "darwin": (
        "chrome-mac/Chromium.app/Contents/MacOS/Chromium",
        "chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium",
    ),
    "linux": ("chrome-linux/chrome",),
}


def _is_existing_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:  # pragma: no cover - defensive, unreadable paths
        return False


def _platform_candidates(platform_name: str, environ: Mapping[str, str]) -> list[str]:
    if platform_name.startswith("win"):
        candidates: list[str] = []
        for env_var in WINDOWS_BASE_ENV_VARS:
            base = environ.get(env_var)
            if not base:
                continue
            for relative in WINDOWS_RELATIVE_PATHS:
                candidates.append(str(Path(base) / relative.replace("\\", os.sep)))
        return candidates
    if platform_name == "darwin":
        return list(MACOS_PATHS)
    return list(LINUX_PATHS)


def discover_system_browsers(
    *,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    which=shutil.which,
    is_file=_is_existing_file,
    extra_candidates: Sequence[str] = (),
) -> list[str]:
    """Return existing Chromium-compatible executables, best candidates first."""

    platform_name = platform_name if platform_name is not None else sys.platform
    environ = environ if environ is not None else os.environ

    found: list[str] = []

    def _add(candidate: str | None) -> None:
        if not candidate:
            return
        path = Path(candidate)
        if not is_file(path):
            return
        resolved = str(path)
        if resolved not in found:
            found.append(resolved)

    for candidate in extra_candidates:
        _add(candidate)
    for candidate in _platform_candidates(platform_name, environ):
        _add(candidate)
    for name in COMMAND_NAMES:
        _add(which(name))
    return found


def _managed_registry_dir(platform_name: str, environ: Mapping[str, str]) -> Path | None:
    configured = environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if configured:
        if configured == "0":
            return None
        return Path(configured)
    if platform_name.startswith("win"):
        local_appdata = environ.get("LOCALAPPDATA")
        if not local_appdata:
            return None
        return Path(local_appdata) / "ms-playwright"
    home = environ.get("HOME")
    if not home:
        return None
    if platform_name == "darwin":
        return Path(home) / "Library" / "Caches" / "ms-playwright"
    return Path(home) / ".cache" / "ms-playwright"


def find_managed_chromium(
    *,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    is_file=_is_existing_file,
) -> str | None:
    """Return the Playwright-managed Chromium path, without downloading it."""

    platform_name = platform_name if platform_name is not None else sys.platform
    environ = environ if environ is not None else os.environ

    registry = _managed_registry_dir(platform_name, environ)
    if registry is None:
        return None
    key = "win32" if platform_name.startswith("win") else ("darwin" if platform_name == "darwin" else "linux")
    relatives = MANAGED_RELATIVE_EXECUTABLES[key]
    try:
        install_dirs: Iterable[Path] = sorted(registry.glob("chromium-*"))
    except OSError:  # pragma: no cover - defensive, unreadable registry
        return None
    for install_dir in install_dirs:
        if install_dir.name.startswith("chromium_headless_shell"):
            continue
        for relative in relatives:
            executable = install_dir / Path(relative.replace("\\", os.sep))
            if is_file(executable):
                return str(executable)
    return None
