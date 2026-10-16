from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .core import DataQualityIssue, validate_record
from .ingestion import load_csv


@dataclass(frozen=True)
class RecordValidationResult:
    record_index: int
    issues: tuple[DataQualityIssue, ...]


def run_pipeline(
    file_path: str | Path,
    required_columns: Iterable[str],
    rules: Mapping[str, Callable[[str], bool]] | None = None,
    unique_fields: Iterable[str] | None = None,
) -> list[RecordValidationResult]:
    """Load a CSV and validate its records."""

    columns = tuple(required_columns)
    records = load_csv(file_path, required_columns=columns)

    results = []

    fields_to_check = tuple(unique_fields or [])
    seen_values = {field: set() for field in fields_to_check}

    for index, record in enumerate(records, start=1):
        issues = validate_record(
            record,
            required_fields=columns,
            rules=rules,
        )

        for field in fields_to_check:
            value = record.get(field)

            if value is None or value == "":
                continue

            if value in seen_values[field]:
                issues.append(
                    DataQualityIssue(
                        field=field,
                        message="Duplicate value.",
                        value=value,
                        expected="unique value",
                    )
                )
            else:
                seen_values[field].add(value)

        results.append(
            RecordValidationResult(
                record_index=index,
                issues=tuple(issues),
            )
        )

    return results
