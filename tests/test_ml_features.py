from pathlib import Path

import pytest

from lucops.ml.features import prepare_csv_features
from lucops.pipeline import run_pipeline
from lucops.rules import is_positive_amount


def write_csv(tmp_path: Path, rows: str) -> Path:
    path = tmp_path / "transactions.csv"
    path.write_text("id_transacao,cliente_id,valor\n" + rows, encoding="utf-8")
    return path


def test_preserves_identity_order_and_extreme_valid_values(tmp_path):
    path = write_csv(tmp_path, "T02,C01,150.00\nT01,C02,50000.00\n")
    original = path.read_bytes()
    result = prepare_csv_features(path)
    assert [
        (r.record_index, r.transaction_id, r.original_value, r.amount)
        for r in result.eligible
    ] == [
        (1, "T02", "150.00", 150.0),
        (2, "T01", "50000.00", 50000.0),
    ]
    assert result.ineligible == ()
    assert path.read_bytes() == original


@pytest.mark.parametrize("value", ["", "abc", "-1", "0", "1.001", "NaN", "Infinity"])
def test_rejects_invalid_financial_values_with_reasons(tmp_path, value):
    result = prepare_csv_features(write_csv(tmp_path, f"T01,C01,{value}\n"))
    assert result.eligible == ()
    (rejected,) = result.ineligible
    assert rejected.record_index == 1
    assert rejected.transaction_id == "T01"
    assert rejected.original_value == value
    assert rejected.issues[0].field == "valor"


def test_reuses_all_quality_issues_and_preserves_alignment(tmp_path):
    path = write_csv(tmp_path, "T01,C01,10.00\nT01,,-2.00\nT03,C03,30.00\n")
    result = prepare_csv_features(path)
    validations = run_pipeline(
        path,
        ["id_transacao", "cliente_id", "valor"],
        rules={"valor": is_positive_amount},
        unique_fields=["id_transacao"],
    )
    assert [r.record_index for r in result.eligible] == [1, 3]
    (rejected,) = result.ineligible
    assert rejected.record_index == 2
    assert rejected.issues == validations[1].issues
    assert len(rejected.issues) == 3


def test_missing_transaction_id_is_ineligible(tmp_path):
    result = prepare_csv_features(write_csv(tmp_path, ",C01,10.00\n"))
    assert result.ineligible[0].transaction_id == ""
    assert result.ineligible[0].issues[0].field == "id_transacao"


@pytest.mark.parametrize("value", ["1e39", "1e400"])
def test_rejects_values_outside_ml_range_without_changing_quality(tmp_path, value):
    path = write_csv(tmp_path, f"T01,C01,{value}\n")
    result = prepare_csv_features(path)
    assert result.eligible == ()
    assert "numeric range" in result.ineligible[0].issues[0].message
    assert (
        run_pipeline(
            path,
            ["id_transacao", "cliente_id", "valor"],
            rules={"valor": is_positive_amount},
        )[0].issues
        == ()
    )


def test_header_only_returns_empty_groups(tmp_path):
    result = prepare_csv_features(write_csv(tmp_path, ""))
    assert result.eligible == result.ineligible == ()


@pytest.mark.parametrize(
    "content",
    [
        "",
        "id_transacao,valor\nT01,10\n",
        "id_transacao,cliente_id,valor\nT01,C01\n",
        "id_transacao,cliente_id,valor\nT01,C01,10,extra\n",
    ],
)
def test_structural_errors_propagate(tmp_path, content):
    path = tmp_path / "invalid.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        prepare_csv_features(path)


def test_missing_file_propagates(tmp_path):
    with pytest.raises(FileNotFoundError):
        prepare_csv_features(tmp_path / "missing.csv")
