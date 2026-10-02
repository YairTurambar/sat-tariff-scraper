"""Configuration loading for the SAT tariff application."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


@dataclass(slots=True)
class AppConfig:
    sat_base_url: str = "https://portal.sat.gob.gt/portal/arancel-integrado/"
    browser_type: str = "chromium"
    headless: bool = False
    persistent_profile_dir: Path = Path("playwright-user-data")
    navigation_timeout_ms: int = 30000
    action_timeout_ms: int = 10000
    max_retries: int = 2
    retry_backoff_factor: float = 2.0
    delay_between_codes_seconds: float = 1.0
    input_file: Path = Path("HS_codes.txt")
    sqlite_db: Path = Path("sat_tariff.db")
    output_xlsx: Path = Path("sat_tariff_example.xlsx")
    artifacts_dir: Path = Path("artifacts")
    logs_dir: Path = Path("logs")
    log_level: str = "INFO"
    overwrite_output: bool = True
    backup_output: bool = True
    invalid_line_policy: str = "skip"
    artifact_retention_count: int = 20

    def ensure_directories(self) -> None:
        self.persistent_profile_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_db.parent.mkdir(parents=True, exist_ok=True)
        self.output_xlsx.parent.mkdir(parents=True, exist_ok=True)


DEFAULT_CONFIG = AppConfig()



def _parse_bool(value: str, default: bool) -> bool:
    lowered = value.strip().lower()
    if lowered in TRUE_VALUES:
        return True
    if lowered in FALSE_VALUES:
        return False
    return default



def _load_optional_dotenv(env_file: Path) -> dict[str, str]:
    if not env_file.exists():
        return {}
    try:
        from dotenv import dotenv_values  # type: ignore

        loaded = dotenv_values(env_file)
        return {key: value for key, value in loaded.items() if value is not None}
    except Exception:
        values: dict[str, str] = {}
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip()
        return values



def load_config(env_file: str | Path = ".env") -> AppConfig:
    env_path = Path(env_file)
    file_values = _load_optional_dotenv(env_path)

    def get(name: str, default: str) -> str:
        return os.environ.get(name, file_values.get(name, default))

    config = AppConfig(
        sat_base_url=get("SAT_BASE_URL", DEFAULT_CONFIG.sat_base_url),
        browser_type=get("SAT_BROWSER_TYPE", DEFAULT_CONFIG.browser_type),
        headless=_parse_bool(get("SAT_HEADLESS", str(DEFAULT_CONFIG.headless).lower()), DEFAULT_CONFIG.headless),
        persistent_profile_dir=Path(get("SAT_PROFILE_DIR", str(DEFAULT_CONFIG.persistent_profile_dir))),
        navigation_timeout_ms=int(get("SAT_NAVIGATION_TIMEOUT_MS", str(DEFAULT_CONFIG.navigation_timeout_ms))),
        action_timeout_ms=int(get("SAT_ACTION_TIMEOUT_MS", str(DEFAULT_CONFIG.action_timeout_ms))),
        max_retries=int(get("SAT_MAX_RETRIES", str(DEFAULT_CONFIG.max_retries))),
        retry_backoff_factor=float(get("SAT_RETRY_BACKOFF_FACTOR", str(DEFAULT_CONFIG.retry_backoff_factor))),
        delay_between_codes_seconds=float(get("SAT_DELAY_BETWEEN_CODES_SECONDS", str(DEFAULT_CONFIG.delay_between_codes_seconds))),
        input_file=Path(get("SAT_INPUT_FILE", str(DEFAULT_CONFIG.input_file))),
        sqlite_db=Path(get("SAT_SQLITE_DB", str(DEFAULT_CONFIG.sqlite_db))),
        output_xlsx=Path(get("SAT_OUTPUT_XLSX", str(DEFAULT_CONFIG.output_xlsx))),
        artifacts_dir=Path(get("SAT_ARTIFACTS_DIR", str(DEFAULT_CONFIG.artifacts_dir))),
        logs_dir=Path(get("SAT_LOGS_DIR", str(DEFAULT_CONFIG.logs_dir))),
        log_level=get("SAT_LOG_LEVEL", DEFAULT_CONFIG.log_level).upper(),
        overwrite_output=_parse_bool(get("SAT_OVERWRITE_OUTPUT", str(DEFAULT_CONFIG.overwrite_output).lower()), DEFAULT_CONFIG.overwrite_output),
        backup_output=_parse_bool(get("SAT_BACKUP_OUTPUT", str(DEFAULT_CONFIG.backup_output).lower()), DEFAULT_CONFIG.backup_output),
        invalid_line_policy=get("SAT_INVALID_LINE_POLICY", DEFAULT_CONFIG.invalid_line_policy),
        artifact_retention_count=int(get("SAT_ARTIFACT_RETENTION_COUNT", str(DEFAULT_CONFIG.artifact_retention_count))),
    )
    return config
