import math
from pathlib import Path

from ..core import DataQualityIssue
from ..ingestion import load_csv
from ..pipeline import run_pipeline
from ..rules import is_positive_amount
from .schemas import IneligibleTransaction, PreparedTransactions, TransactionFeatures

_REQUIRED_COLUMNS = ("id_transacao", "cliente_id", "valor")
# Isolation Forest converts its input to float32 internally.
_MAX_FLOAT32 = 3.4028234663852886e38


def prepare_csv_features(file_path: str | Path) -> PreparedTransactions:
    """Prepare the single attribute valor without changing quality results.

    Indices are one-based data record indices, as in run_pipeline.
    Structural CSV errors propagate. Invalid records retain all quality issues.
    No model is trained and no input file is modified.
    """
    records = load_csv(file_path, required_columns=_REQUIRED_COLUMNS)
    validations = run_pipeline(
        file_path,
        required_columns=_REQUIRED_COLUMNS,
        rules={"valor": is_positive_amount},
        unique_fields=["id_transacao"],
    )
    eligible = []
    ineligible = []

    for record, validation in zip(records, validations, strict=True):
        issues = validation.issues
        amount = None
        if not issues:
            amount = float(record["valor"])
            if not math.isfinite(amount) or amount > _MAX_FLOAT32 or amount <= 0:
                issues = (
                    DataQualityIssue(
                        field="valor",
                        message="Value is outside the supported ML numeric range.",
                        value=record["valor"],
                        expected="positive finite float32 value",
                    ),
                )

        identity = {
            "record_index": validation.record_index,
            "transaction_id": record["id_transacao"],
            "original_value": record["valor"],
        }
        if issues:
            ineligible.append(IneligibleTransaction(**identity, issues=issues))
        else:
            eligible.append(TransactionFeatures(**identity, amount=amount))

    return PreparedTransactions(tuple(eligible), tuple(ineligible))
