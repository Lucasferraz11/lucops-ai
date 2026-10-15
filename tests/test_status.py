import pytest

from lucops.status import get_quality_status
from lucops.summary import DataQualitySummary


@pytest.mark.parametrize(
    ("total_records", "invalid_records", "expected"),
    [
        (0, 0, "SEM DADOS"),
        (3, 1, "COM INCONSISTÊNCIAS"),
        (3, 0, "SEM INCONSISTÊNCIAS"),
    ],
)
def test_get_quality_status(
    total_records: int,
    invalid_records: int,
    expected: str,
):
    valid_records = total_records - invalid_records

    summary = DataQualitySummary(
        total_records=total_records,
        valid_records=valid_records,
        invalid_records=invalid_records,
        total_issues=invalid_records,
        valid_percentage=(
            None
            if total_records == 0
            else round(valid_records / total_records * 100, 2)
        ),
    )

    assert get_quality_status(summary) == expected
