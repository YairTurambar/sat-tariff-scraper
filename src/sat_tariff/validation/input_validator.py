"""Input validation for HS code files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..models import HsCodeEntry

MIN_HS_LENGTH = 4
MAX_HS_LENGTH = 10
MAX_LINES = 500


class InputValidationError(ValueError):
    pass


@dataclass(slots=True)
class InputValidationResult:
    entries: list[HsCodeEntry]
    duplicate_codes: list[str] = field(default_factory=list)
    suspicious_codes: list[str] = field(default_factory=list)
    total_lines: int = 0



def classify_hs_code(raw_code: str) -> tuple[str, bool, list[str]]:
    normalized = raw_code.strip()
    notes: list[str] = []
    suspicious = False
    if not normalized.isdigit():
        suspicious = True
        notes.append("contains non-digit characters")
    if not (MIN_HS_LENGTH <= len(normalized) <= MAX_HS_LENGTH):
        suspicious = True
        notes.append(f"length outside expected range {MIN_HS_LENGTH}-{MAX_HS_LENGTH}")
    return normalized, suspicious, notes



def validate_hs_codes(lines: list[str], invalid_policy: str = "skip") -> InputValidationResult:
    stripped = [line.strip() for line in lines if line.strip()]
    total_lines = len(stripped)
    if total_lines == 0:
        raise InputValidationError("HS_codes.txt must contain at least 1 non-empty line.")
    if total_lines > MAX_LINES:
        raise InputValidationError(f"HS_codes.txt exceeds the maximum of {MAX_LINES} non-empty lines.")

    duplicate_codes: list[str] = []
    suspicious_codes: list[str] = []
    entries: list[HsCodeEntry] = []
    seen: set[str] = set()

    for raw_code in stripped:
        normalized, suspicious, notes = classify_hs_code(raw_code)
        if normalized in seen:
            duplicate_codes.append(normalized)
            continue
        seen.add(normalized)
        if suspicious:
            suspicious_codes.append(raw_code)
            if invalid_policy == "skip":
                continue
        entries.append(HsCodeEntry(raw_code=raw_code, normalized_code=normalized, is_suspicious=suspicious, notes=notes))

    return InputValidationResult(
        entries=entries,
        duplicate_codes=duplicate_codes,
        suspicious_codes=suspicious_codes,
        total_lines=total_lines,
    )



def validate_hs_code_file(path: str | Path, invalid_policy: str = "skip") -> InputValidationResult:
    file_path = Path(path)
    lines = file_path.read_text(encoding="utf-8").splitlines()
    return validate_hs_codes(lines, invalid_policy=invalid_policy)
