"""Core models for SAT tariff processing."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ProcessingState(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    rights_completed = "rights_completed"
    nomenclature_completed = "nomenclature_completed"
    restrictions_completed = "restrictions_completed"
    quotas_completed = "quotas_completed"
    completed = "completed"
    retryable_error = "retryable_error"
    permanent_error = "permanent_error"
    captcha_required = "captcha_required"


@dataclass(slots=True)
class HsCodeEntry:
    raw_code: str
    normalized_code: str
    is_suspicious: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RightsTaxesRow:
    agreement_name: str
    code: str
    description: str
    additional_code: str
    value: str
    quota_code: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class NomenclatureRecord:
    record_type: str
    section: str
    chapter: str
    effective_from_raw: str
    effective_from_normalized: str | None
    effective_to_raw: str
    effective_to_normalized: str | None
    additional_codes_text: str
    unit_code: str
    unit_description: str
    source_status: str
    code: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RestrictionRecord:
    code: str
    description: str
    additional_code: str
    value: str
    quota_code: str
    source_status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QuotaRecord:
    treatment_name: str
    message: str
    source_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
