from collections.abc import Iterable
from dataclasses import dataclass

from .pipeline import RecordValidationResult


@dataclass(frozen=True)
class DataQualitySummary:
    total_records: int
    valid_records: int
    invalid_records: int
    total_issues: int
    valid_percentage: float | None


def summarize_results(
    results: Iterable[RecordValidationResult],
) -> DataQualitySummary:
    """Calculate quality metrics from validation results."""

    total_records = 0
    valid_records = 0
    invalid_records = 0
    total_issues = 0

    for result in results:
        total_records += 1
        total_issues += len(result.issues)

        if result.issues:
            invalid_records += 1
        else:
            valid_records += 1

    valid_percentage = (
        round(valid_records / total_records * 100, 2)
        if total_records > 0
        else None
    )

    return DataQualitySummary(
        total_records=total_records,
        valid_records=valid_records,
        invalid_records=invalid_records,
        total_issues=total_issues,
        valid_percentage=valid_percentage,
    )
