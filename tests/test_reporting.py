from pathlib import Path

from lucops.reporting import format_quality_report, save_quality_report
from lucops.summary import DataQualitySummary


def test_report_with_invalid_records():
    summary = DataQualitySummary(
        total_records=4,
        valid_records=1,
        invalid_records=3,
        total_issues=3,
        valid_percentage=25.0,
    )

    report = format_quality_report(summary)

    assert "Registros analisados: 4" in report
    assert "Registros válidos: 1" in report
    assert "Registros inválidos: 3" in report
    assert "Total de inconsistências: 3" in report
    assert "Taxa de validade: 25.00%" in report


def test_report_with_empty_results():
    summary = DataQualitySummary(
        total_records=0,
        valid_records=0,
        invalid_records=0,
        total_issues=0,
        valid_percentage=None,
    )

    report = format_quality_report(summary)

    assert "Registros analisados: 0" in report
    assert "Taxa de validade: N/A (sem registros)" in report


def test_report_formats_percentage_with_two_decimals():
    summary = DataQualitySummary(
        total_records=3,
        valid_records=1,
        invalid_records=2,
        total_issues=2,
        valid_percentage=33.33,
    )

    report = format_quality_report(summary)

    assert "Taxa de validade: 33.33%" in report


def test_save_quality_report_creates_file(tmp_path: Path):
    output_path = tmp_path / "reports" / "quality_report.txt"

    report = (
        "RELATÓRIO DE QUALIDADE DE DADOS\n"
        "Registros válidos: 4"
    )

    saved_path = save_quality_report(report, output_path)

    assert saved_path == output_path
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == report


def test_save_quality_report_overwrites_existing_file(
    tmp_path: Path,
):
    output_path = tmp_path / "quality_report.txt"

    output_path.write_text(
        "Relatório anterior",
        encoding="utf-8",
    )

    save_quality_report(
        "Novo relatório",
        output_path,
    )

    assert output_path.read_text(
        encoding="utf-8",
    ) == "Novo relatório"
