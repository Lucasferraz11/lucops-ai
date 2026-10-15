from .summary import DataQualitySummary


def get_quality_status(summary: DataQualitySummary) -> str:
    """Determine the quality status of an analysis."""

    if summary.total_records == 0:
        return "SEM DADOS"

    if summary.invalid_records > 0:
        return "COM INCONSISTÊNCIAS"

    return "SEM INCONSISTÊNCIAS"
