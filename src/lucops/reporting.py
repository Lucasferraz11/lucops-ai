from pathlib import Path

from .summary import DataQualitySummary


def format_quality_report(summary: DataQualitySummary) -> str:
    """Format quality metrics as a readable text report."""

    percentage = (
        f"{summary.valid_percentage:.2f}%"
        if summary.valid_percentage is not None
        else "N/A (sem registros)"
    )

    return (
        "RELATÓRIO DE QUALIDADE DE DADOS\n"
        "------------------------------\n"
        f"Registros analisados: {summary.total_records}\n"
        f"Registros válidos: {summary.valid_records}\n"
        f"Registros inválidos: {summary.invalid_records}\n"
        f"Total de inconsistências: {summary.total_issues}\n"
        f"Taxa de validade: {percentage}"
    )


def save_quality_report(
    report: str,
    output_path: str | Path,
) -> Path:
    """Save a quality report to a text file."""

    path = Path(output_path)

    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(report, encoding="utf-8")

    return path
