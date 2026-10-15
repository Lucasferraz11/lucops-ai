from pathlib import Path

from lucops.pipeline import run_pipeline
from lucops.rules import is_positive_amount


def test_pipeline_detects_missing_required_field(
    tmp_path: Path,
):
    # Cria um arquivo CSV temporario
    csv_file = tmp_path / "transacoes.csv"

    csv_file.write_text(
        "id_transacao,cliente_id,valor\n"
        "T001,C001,150.00\n"
        "T002,,220.50\n",
        encoding="utf-8",
    )

    # Executa o pipeline completo
    results = run_pipeline(
        file_path=csv_file,
        required_columns=[
            "id_transacao",
            "cliente_id",
            "valor",
        ],
    )

    # Confirma que analisou os dois registros
    assert len(results) == 2

    # Primeiro registro: valido
    assert results[0].record_index == 1
    assert results[0].issues == ()

    # Segundo registro: cliente ausente
    assert results[1].record_index == 2
    assert len(results[1].issues) == 1
    assert results[1].issues[0].field == "cliente_id"
    assert results[1].issues[0].message == "Field is required."



def test_pipeline_applies_financial_rule(tmp_path: Path):
    csv_file = tmp_path / "transacoes.csv"

    csv_file.write_text(
        "id_transacao,cliente_id,valor\n"
        "T001,C001,150.00\n"
        "T002,C002,-20.00\n"
        "T003,C003,abc\n",
        encoding="utf-8",
    )

    results = run_pipeline(
        file_path=csv_file,
        required_columns=[
            "id_transacao",
            "cliente_id",
            "valor",
        ],
        rules={"valor": is_positive_amount},
    )

    assert len(results) == 3

    # Transacao com valor positivo
    assert results[0].issues == ()

    # Transacao com valor negativo
    assert len(results[1].issues) == 1
    assert results[1].issues[0].field == "valor"
    assert results[1].issues[0].message == "Rule failed."

    # Transacao com valor nao numerico
    assert len(results[2].issues) == 1
    assert results[2].issues[0].field == "valor"
    assert results[2].issues[0].message == "Rule failed."

def test_pipeline_detects_duplicate_transactions(
    tmp_path: Path,
):
    csv_file = tmp_path / "transacoes.csv"

    csv_file.write_text(
        "id_transacao,cliente_id,valor\n"
        "T001,C001,150.00\n"
        "T002,C002,200.00\n"
        "T001,C003,350.00\n",
        encoding="utf-8",
    )

    results = run_pipeline(
        file_path=csv_file,
        required_columns=[
            "id_transacao",
            "cliente_id",
            "valor",
        ],
        rules={"valor": is_positive_amount},
        unique_fields=["id_transacao"],
    )

    assert len(results) == 3

    assert results[0].issues == ()
    assert results[1].issues == ()

    assert len(results[2].issues) == 1
    assert results[2].issues[0].field == "id_transacao"
    assert results[2].issues[0].message == "Duplicate value."
    assert results[2].issues[0].value == "T001"
