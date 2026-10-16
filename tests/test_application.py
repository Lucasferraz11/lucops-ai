from pathlib import Path

import pytest

from lucops.application import analyze_csv
from lucops.rules import is_positive_amount


def test_analyze_csv_generates_complete_result(
    tmp_path: Path,
):
    csv_file = tmp_path / "transacoes.csv"
    output_file = tmp_path / "reports" / "analise.txt"

    csv_file.write_text(
        "id_transacao,cliente_id,valor\n"
        "T001,C001,150.00\n"
        "T002,C002,-20.00\n"
        "T003,,80.00\n",
        encoding="utf-8",
    )

    result = analyze_csv(
        file_path=csv_file,
        output_path=output_file,
        required_columns=[
            "id_transacao",
            "cliente_id",
            "valor",
        ],
        rules={"valor": is_positive_amount},
    )

    assert result.summary.total_records == 3
    assert result.summary.valid_records == 1
    assert result.summary.invalid_records == 2
    assert result.summary.total_issues == 2
    assert result.summary.valid_percentage == 33.33

    assert result.saved_path == output_file
    assert output_file.exists()

    saved_report = output_file.read_text(encoding="utf-8")

    assert saved_report == result.report
    assert "Registros analisados: 3" in saved_report
    assert "Taxa de validade: 33.33%" in saved_report


def test_analyze_csv_rejects_missing_columns(
    tmp_path: Path,
):
    csv_file = tmp_path / "transacoes_invalidas.csv"
    output_file = tmp_path / "reports" / "analise.txt"

    csv_file.write_text(
        "id_transacao,valor\nT001,150.00\nT002,200.00\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Missing required CSV columns: cliente_id",
    ):
        analyze_csv(
            file_path=csv_file,
            output_path=output_file,
            required_columns=[
                "id_transacao",
                "cliente_id",
                "valor",
            ],
            rules={"valor": is_positive_amount},
        )

    assert not output_file.exists()


def test_complete_data_quality_analysis(tmp_path: Path):
    csv_file = tmp_path / "transacoes.csv"
    output_file = tmp_path / "reports" / "analise.txt"

    csv_file.write_text(
        "id_transacao,cliente_id,valor\n"
        "T001,C001,150.00\n"
        "T002,C002,-20.00\n"
        "T001,C003,10.999\n"
        "T004,,80.00\n",
        encoding="utf-8",
    )

    result = analyze_csv(
        file_path=csv_file,
        output_path=output_file,
        required_columns=[
            "id_transacao",
            "cliente_id",
            "valor",
        ],
        rules={"valor": is_positive_amount},
        unique_fields=["id_transacao"],
    )

    assert result.summary.total_records == 4
    assert result.summary.valid_records == 1
    assert result.summary.invalid_records == 3
    assert result.summary.total_issues == 4
    assert result.summary.valid_percentage == 25.0

    assert output_file.exists()
    assert result.saved_path == output_file

    report = output_file.read_text(encoding="utf-8")

    assert report == result.report
    assert "Total de inconsistências: 4" in report
    assert "Taxa de validade: 25.00%" in report
