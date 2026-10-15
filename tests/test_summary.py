from lucops.core import DataQualityIssue
from lucops.pipeline import RecordValidationResult
from lucops.summary import DataQualitySummary, summarize_results


def test_summary_with_valid_and_invalid_records():
    results = [
        RecordValidationResult(
            record_index=1,
            issues=(),
        ),
        RecordValidationResult(
            record_index=2,
            issues=(
                DataQualityIssue(
                    field="valor",
                    message="Rule failed.",
                ),
            ),
        ),
        RecordValidationResult(
            record_index=3,
            issues=(
                DataQualityIssue(
                    field="valor",
                    message="Rule failed.",
                ),
                DataQualityIssue(
                    field="cliente_id",
                    message="Field is required.",
                ),
            ),
        ),
    ]

    summary = summarize_results(results)

    assert summary == DataQualitySummary(
        total_records=3,
        valid_records=1,
        invalid_records=2,
        total_issues=3,
        valid_percentage=33.33,
    )


def test_summary_with_all_valid_records():
    results = [
        RecordValidationResult(record_index=1, issues=()),
        RecordValidationResult(record_index=2, issues=()),
    ]

    summary = summarize_results(results)

    assert summary == DataQualitySummary(
        total_records=2,
        valid_records=2,
        invalid_records=0,
        total_issues=0,
        valid_percentage=100.0,
    )


def test_summary_with_empty_results():
    summary = summarize_results([])

    assert summary == DataQualitySummary(
        total_records=0,
        valid_records=0,
        invalid_records=0,
        total_issues=0,
        valid_percentage=None,
    )
