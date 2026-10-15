import subprocess
import sys
from pathlib import Path


def test_cli_generates_quality_report(tmp_path: Path):
    csv_file = tmp_path / "transacoes.csv"

    csv_file.write_text(
        "id_transacao,cliente_id,valor\n"
        "T001,C001,150.00\n"
        "T002,C002,-20.00\n"
        "T003,C003,abc\n",
        encoding="utf-8",
    )

    output_file = tmp_path / "reports" / "resultado.txt"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "lucops",
            str(csv_file),
            "--output",
            str(output_file),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert output_file.exists()

    report = output_file.read_text(encoding="utf-8")

    assert "Registros analisados: 3" in report
    assert "Registros válidos: 1" in report
    assert "Registros inválidos: 2" in report
    assert "Taxa de validade: 33.33%" in report

    assert "Relatório salvo em:" in result.stdout
    assert "Status da qualidade: COM INCONSISTÊNCIAS" in result.stdout


def test_cli_reports_missing_csv(tmp_path: Path):
    missing_file = tmp_path / "nao_existe.csv"
    output_file = tmp_path / "reports" / "resultado.txt"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "lucops",
            str(missing_file),
            "--output",
            str(output_file),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 2
    assert "Arquivo CSV não encontrado:" in result.stderr
    assert str(missing_file) in result.stderr
    assert "Traceback" not in result.stderr
    assert not output_file.exists()


def test_cli_reports_missing_required_columns(tmp_path: Path):
    csv_file = tmp_path / "transacoes.csv"
    output_file = tmp_path / "reports" / "resultado.txt"

    csv_file.write_text(
        "id_transacao,valor\n"
        "T001,150.00\n"
        "T002,200.00\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "lucops",
            str(csv_file),
            "--output",
            str(output_file),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 2
    assert "CSV inválido:" in result.stderr
    assert "Missing required CSV columns: cliente_id" in result.stderr
    assert "Traceback" not in result.stderr
    assert not output_file.exists()


def test_cli_rejects_incomplete_csv_row(tmp_path: Path):
    csv_file = tmp_path / "transacoes.csv"
    output_file = tmp_path / "reports" / "resultado.txt"

    csv_file.write_text(
        "id_transacao,cliente_id,valor\n"
        "T001,C001,150.00\n"
        "T002,C002\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "lucops",
            str(csv_file),
            "--output",
            str(output_file),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 2
    assert "CSV inválido:" in result.stderr
    assert "CSV record 3 has fewer values than columns." in result.stderr
    assert "Traceback" not in result.stderr
    assert not output_file.exists()


def test_cli_reports_no_inconsistencies(tmp_path: Path):
    csv_file = tmp_path / "transacoes_validas.csv"
    output_file = tmp_path / "reports" / "resultado.txt"

    csv_file.write_text(
        "id_transacao,cliente_id,valor\n"
        "T001,C001,150.00\n"
        "T002,C002,200.00\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "lucops",
            str(csv_file),
            "--output",
            str(output_file),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Status da qualidade: SEM INCONSISTÊNCIAS" in result.stdout
    assert "Registros válidos: 2" in result.stdout
    assert "Registros inválidos: 0" in result.stdout
    assert output_file.exists()


def test_cli_reports_empty_dataset(tmp_path: Path):
    csv_file = tmp_path / "transacoes_vazias.csv"
    output_file = tmp_path / "reports" / "resultado.txt"

    csv_file.write_text(
        "id_transacao,cliente_id,valor\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "lucops",
            str(csv_file),
            "--output",
            str(output_file),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Status da qualidade: SEM DADOS" in result.stdout
    assert "Registros analisados: 0" in result.stdout
    assert "Taxa de validade: N/A (sem registros)" in result.stdout

    assert output_file.exists()

    report = output_file.read_text(encoding="utf-8")

    assert "Registros analisados: 0" in report
    assert "Taxa de validade: N/A (sem registros)" in report


def test_cli_detects_duplicate_transactions(tmp_path: Path):
    csv_file = tmp_path / "transacoes.csv"
    output_file = tmp_path / "reports" / "resultado.txt"

    csv_file.write_text(
        "id_transacao,cliente_id,valor\n"
        "T001,C001,150.00\n"
        "T002,C002,200.00\n"
        "T001,C003,350.00\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "lucops",
            str(csv_file),
            "--output",
            str(output_file),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Registros analisados: 3" in result.stdout
    assert "Registros válidos: 2" in result.stdout
    assert "Registros inválidos: 1" in result.stdout
    assert "Total de inconsistências: 1" in result.stdout
    assert "Status da qualidade: COM INCONSISTÊNCIAS" in result.stdout
    assert output_file.exists()
