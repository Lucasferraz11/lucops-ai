from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DataQualityIssue:
    field: str
    message: str
    value: Any = None
    expected: Any = None


def validate_record(
    record: Mapping[str, Any],
    required_fields: Iterable[str] | None = None,
    rules: Mapping[str, Callable[[Any], bool]] | None = None,
) -> list[DataQualityIssue]:
    """Validate a record against required fields and custom rules."""
    if not isinstance(record, Mapping):
        raise TypeError("record must be a mapping-like object")

    issues: list[DataQualityIssue] = []
    required = set(required_fields or [])

    for field in sorted(required):
        if field not in record or record.get(field) in (None, ""):
            issues.append(
                DataQualityIssue(
                    field=field,
                    message="Field is required.",
                    value=record.get(field),
                    expected="present and not empty",
                )
            )

    for field, rule in (rules or {}).items():
        if field not in record:
            continue

        value = record[field]
        if value in (None, ""):
            continue

        try:
            is_valid = bool(rule(value))
        except (ValueError, TypeError) as exc:
            issues.append(
                DataQualityIssue(
                    field=field,
                    message=f"Rule failed: {exc}",
                    value=value,
                    expected="rule evaluation succeeded",
                )
            )
            continue

        if not is_valid:
            issues.append(
                DataQualityIssue(
                    field=field,
                    message="Rule failed.",
                    value=value,
                    expected="rule check passed",
                )
            )

    return issues
