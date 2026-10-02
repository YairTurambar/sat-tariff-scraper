"""Resume-point helpers for SAT tariff scraping."""

from __future__ import annotations

from dataclasses import dataclass

from .models import ProcessingState

SECTION_SEQUENCE = ("rights", "nomenclature", "restrictions", "quotas")


@dataclass(slots=True, frozen=True)
class ResumePoint:
    code: str
    state: ProcessingState
    next_section: str | None


def next_section_for_state(state: ProcessingState) -> str | None:
    mapping = {
        ProcessingState.pending: "rights",
        ProcessingState.in_progress: "rights",
        ProcessingState.rights_completed: "nomenclature",
        ProcessingState.nomenclature_completed: "restrictions",
        ProcessingState.restrictions_completed: "quotas",
        ProcessingState.quotas_completed: None,
        ProcessingState.completed: None,
        ProcessingState.retryable_error: "rights",
        ProcessingState.permanent_error: None,
        ProcessingState.captcha_required: "rights",
    }
    return mapping[state]


def next_section_from_processed_sections(
    state: ProcessingState,
    processed_sections: set[str] | None = None,
) -> str | None:
    if state in {ProcessingState.completed, ProcessingState.permanent_error, ProcessingState.quotas_completed}:
        return None
    if processed_sections:
        for section in SECTION_SEQUENCE:
            if section not in processed_sections:
                return section
        return None
    return next_section_for_state(state)


def build_resume_point(
    code: str,
    state_value: str,
    processed_sections: set[str] | None = None,
) -> ResumePoint:
    state = ProcessingState(state_value)
    return ResumePoint(
        code=code,
        state=state,
        next_section=next_section_from_processed_sections(state, processed_sections),
    )
