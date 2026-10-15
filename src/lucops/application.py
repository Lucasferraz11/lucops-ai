
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .pipeline import run_pipeline
from .reporting import format_quality_report, save_quality_report
from .summary import DataQualitySummary, summarize_results


@dataclass(frozen=True)
class AnalysisResult:
    summary: DataQualitySummary
    report: str
    saved_path: Path


def analyze_csv(
    file_path: str | Path,
    output_path: str | Path,
    required_columns: Iterable[str],
    rules: Mapping[str, Callable[[str], bool]] | None = None,
    unique_fields: Iterable[str] | None = None,
) -> AnalysisResult:
    """Run a complete data quality analysis."""

    results = run_pipeline(
        file_path=file_path,
        required_columns=required_columns,
        rules=rules,
        unique_fields=unique_fields,
    )

    summary = summarize_results(results)

    report = format_quality_report(summary)

    saved_path = save_quality_report(
        report,
        output_path,
    )

    return AnalysisResult(
        summary=summary,
        report=report,
        saved_path=saved_path,
    )
