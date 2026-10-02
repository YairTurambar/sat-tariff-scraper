from sat_tariff.models import ProcessingState


def test_processing_state_values_match_spec_exactly():
    assert [state.value for state in ProcessingState] == [
        "pending",
        "in_progress",
        "rights_completed",
        "nomenclature_completed",
        "restrictions_completed",
        "quotas_completed",
        "completed",
        "retryable_error",
        "permanent_error",
        "captcha_required",
    ]
