from pathlib import Path

import pytest

from lucops.ingestion import load_csv


def test_load_csv_reads_valid_file(tmp_path: Path):
    # Cria um arquivo CSV temporario
    csv_file = tmp_path / "transacoes.csv"

    csv_file.write_text(
        "id_transacao,cliente_id,valor\nT001,C001,150.00\nT002,C002,220.50\n",
        encoding="utf-8",
    )

    # Executa a funcao de ingestao
    records = load_csv(csv_file)

    # Verifica os resultados
    assert len(records) == 2

    assert records[0] == {
        "id_transacao": "T001",
        "cliente_id": "C001",
        "valor": "150.00",
    }

    assert records[1]["valor"] == "220.50"


def test_load_csv_rejects_empty_file(tmp_path: Path):
    # Cria um arquivo CSV completamente vazio
    csv_file = tmp_path / "empty.csv"
    csv_file.write_text("", encoding="utf-8")

    # Verifica se a funcao identifica o problema
    with pytest.raises(
        ValueError,
        match="CSV file must contain a header",
    ):
        load_csv(csv_file)


def test_load_csv_with_header_only(tmp_path: Path):
    # Cria um CSV com cabecalho, mas sem registros
    csv_file = tmp_path / "header_only.csv"

    csv_file.write_text(
        "id_transacao,cliente_id,valor,status\n",
        encoding="utf-8",
    )

    # Executa a leitura do arquivo
    records = load_csv(csv_file)

    # Verifica se retornou uma lista vazia
    assert records == []


def test_load_csv_file_not_found(tmp_path: Path):
    # Define um caminho para um arquivo inexistente
    csv_file = tmp_path / "arquivo_inexistente.csv"

    # Verifica se a funcao gera o erro esperado
    with pytest.raises(FileNotFoundError):
        load_csv(csv_file)


def test_load_csv_rejects_missing_required_columns(
    tmp_path: Path,
):
    csv_file = tmp_path / "missing_columns.csv"

    csv_file.write_text(
        "id_transacao,valor\nT001,150.00\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Missing required CSV columns: cliente_id",
    ):
        load_csv(
            csv_file,
            required_columns=[
                "id_transacao",
                "cliente_id",
                "valor",
            ],
        )


def test_load_csv_rejects_extra_values(tmp_path: Path):
    csv_file = tmp_path / "extra_values.csv"

    csv_file.write_text(
        "id_transacao,cliente_id,valor\nT001,C001,150.00\nT002,C002,220.50,EXTRA\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="CSV record 3 has more values than columns",
    ):
        load_csv(csv_file)


def test_load_csv_rejects_missing_values(tmp_path: Path):
    csv_file = tmp_path / "missing_values.csv"

    csv_file.write_text(
        "id_transacao,cliente_id,valor\nT001,C001,150.00\nT002,C002\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="CSV record 3 has fewer values than columns",
    ):
        load_csv(csv_file)
