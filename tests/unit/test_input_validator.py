from sat_tariff.validation.input_validator import InputValidationError, validate_hs_codes


def test_accepts_one_line_boundary():
    result = validate_hs_codes(["0001"])
    assert [entry.raw_code for entry in result.entries] == ["0001"]


def test_accepts_five_hundred_lines_boundary():
    lines = [f"{index:04d}" for index in range(500)]
    result = validate_hs_codes(lines)
    assert len(result.entries) == 500


def test_rejects_zero_lines():
    try:
        validate_hs_codes([])
    except InputValidationError as exc:
        assert "at least 1" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected validation error")


def test_rejects_more_than_five_hundred_lines():
    lines = [f"{index:04d}" for index in range(501)]
    try:
        validate_hs_codes(lines)
    except InputValidationError as exc:
        assert "maximum of 500" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected validation error")


def test_preserves_leading_zeroes_and_dedupes_duplicates():
    result = validate_hs_codes(["0012", "0012", "00001234"])
    assert [entry.raw_code for entry in result.entries] == ["0012", "00001234"]
    assert result.duplicate_codes == ["0012"]


def test_suspicious_format_skipped_when_policy_skip():
    result = validate_hs_codes(["12AB", "1234"], invalid_policy="skip")
    assert [entry.raw_code for entry in result.entries] == ["1234"]
    assert result.suspicious_codes == ["12AB"]


def test_suspicious_format_processed_when_policy_process():
    result = validate_hs_codes(["12AB", "1234"], invalid_policy="process")
    assert [entry.raw_code for entry in result.entries] == ["12AB", "1234"]
    assert result.entries[0].is_suspicious is True
