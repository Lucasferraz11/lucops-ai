from dataclasses import FrozenInstanceError

import pytest

from lucops import DataQualityIssue, validate_record


def test_validate_record_flags_missing_required_field():
    issues = validate_record({"name": "Ana"}, required_fields=["name", "email"])

    assert any(issue.field == "email" and issue.message == "Field is required." for issue in issues)


def test_validate_record_flags_rule_failures():
    issues = validate_record(
        {"name": "Ana", "age": -1},
        required_fields=["name", "age"],
        rules={"age": lambda value: value >= 0},
    )

    assert any(issue.field == "age" and issue.message == "Rule failed." for issue in issues)


def test_validate_record_accepts_valid_record():
    issues = validate_record(
        {"name": "Ana", "email": "ana@example.com", "age": 30},
        required_fields=["name", "email", "age"],
        rules={"age": lambda value: value >= 0},
    )

    assert issues == []


def test_data_quality_issue_is_immutable():
    issue = DataQualityIssue(
        field="status",
        message="Invalid status",
        value="draft",
    )

    assert issue.field == "status"
    assert issue.message == "Invalid status"
    assert issue.value == "draft"

    with pytest.raises(FrozenInstanceError):
        issue.field = "approved"


def test_validate_record_handles_invalid_value():
    issues = validate_record(
        record={"valor": "abc"},
        rules={"valor": lambda value: float(value) > 0},
    )

    assert len(issues) == 1
    assert issues[0].field == "valor"
    assert issues[0].message.startswith("Rule failed:")


def test_validate_record_propagates_unexpected_error():
    def broken_rule(value):
        raise RuntimeError("Unexpected error")

    with pytest.raises(RuntimeError):
        validate_record(
            record={"valor": 100},
            rules={"valor": broken_rule},
        )

