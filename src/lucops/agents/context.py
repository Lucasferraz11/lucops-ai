"""Build verified context locally, without browser-supplied predictions or AI.

A private snapshot aligns all existing file-based readers without changing
their contracts. Dataset hashes identify exact bytes, not anonymized data.
Only the selected record is exposed; identifiers and arbitrary text are omitted.
"""

import hashlib
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import TemporaryDirectory

from ..ingestion import load_csv
from ..ml.features import prepare_csv_features
from ..pipeline import run_pipeline
from ..rules import is_positive_amount
from .schemas import (
    Evidence,
    EvidenceSource,
    InvestigationContext,
    MLInformation,
    MLStatus,
    QualityInconsistency,
    TransactionContext,
)

_REQUIRED_COLUMNS = ("id_transacao", "cliente_id", "valor")


def _minimize_value(field: str, value: str | None) -> str | None:
    """Keep missingness and bounded numeric amounts, never personal IDs/text."""
    if value in (None, ""):
        return value
    if field == "valor" and len(value) <= 64:
        try:
            if Decimal(value).is_finite():
                return value
        except InvalidOperation:
            pass
    return "[redacted]"


def _ml_information(snapshot: Path, record_index: int, add_evidence, include_ml: bool):
    prepared = prepare_csv_features(snapshot)
    rejected = next(
        (r for r in prepared.ineligible if r.record_index == record_index), None
    )
    if rejected is not None:
        reasons = tuple(f"{issue.field}: {issue.message}" for issue in rejected.issues)
        evidence_id = add_evidence(
            "ml",
            "lucops.ml.features.prepare_csv_features",
            "eligibility",
            "Registro inelegível para ML conforme as regras atuais de preparação.",
            "ineligible",
        )
        return MLInformation(
            status=MLStatus.INELIGIBLE, reasons=reasons, evidence_ids=(evidence_id,)
        )

    if not include_ml:
        return MLInformation(
            status=MLStatus.UNAVAILABLE,
            reasons=("A análise de ML não foi solicitada.",),
        )

    try:
        from ..ml.service import ModelUnavailableError, analyze_csv_anomalies
    except ImportError:
        return MLInformation(
            status=MLStatus.UNAVAILABLE,
            reasons=("Dependências opcionais de ML indisponíveis.",),
        )
    try:
        analysis = analyze_csv_anomalies(snapshot)
    except ModelUnavailableError:
        return MLInformation(
            status=MLStatus.UNAVAILABLE,
            reasons=("O modelo de ML configurado no servidor está indisponível.",),
        )

    prediction = next(
        (r for r in analysis["results"] if r["record_index"] == record_index), None
    )
    if prediction is None:
        raise ValueError(
            "Server ML result does not contain the selected eligible record."
        )
    # Validate the internal result before recording it as evidence.
    info = MLInformation(
        status=MLStatus.EVALUATED,
        model_version=analysis["model_version"],
        anomaly_score=prediction["anomaly_score"],
        is_anomaly=prediction["is_anomaly"],
    )
    evidence_ids = tuple(
        add_evidence(
            "ml",
            "lucops.ml.service.analyze_csv_anomalies",
            field,
            description,
            value,
        )
        for field, description, value in (
            (
                "model_version",
                "Versão declarada pelo modelo configurado no servidor.",
                info.model_version,
            ),
            (
                "anomaly_score",
                "Negativo da decision_function; não é probabilidade.",
                info.anomaly_score,
            ),
            (
                "is_anomaly",
                "Alerta estatístico do detector de ML existente.",
                info.is_anomaly,
            ),
        )
    )
    return MLInformation(
        status=info.status,
        model_version=info.model_version,
        anomaly_score=info.anomaly_score,
        is_anomaly=info.is_anomaly,
        evidence_ids=evidence_ids,
    )


def build_investigation_context(
    file_path: str | Path,
    record_index: int,
    *,
    include_ml: bool = True,
) -> InvestigationContext:
    """Build a context from a server-owned CSV and a one-based data record index.

    This is a server-side function, not a public file-path API. No model paths,
    scores, or quality results are accepted from callers. Structural CSV errors
    propagate. A missing selected record raises IndexError.
    No training, external calls, source-file changes, or permanent writes occur.
    """
    if type(record_index) is not int or record_index < 1:
        raise ValueError("record_index must be a positive integer.")
    payload = Path(file_path).read_bytes()
    dataset_id = "sha256:" + hashlib.sha256(payload).hexdigest()
    evidence = []

    def add_evidence(kind, function, field, description, value, expected=None):
        evidence_id = f"{dataset_id}:record:{record_index}:e{len(evidence) + 1}"
        evidence.append(
            Evidence(
                evidence_id=evidence_id,
                kind=kind,
                source=EvidenceSource(dataset_id, record_index, function, field),
                description=description,
                value=value,
                expected=expected,
            )
        )
        return evidence_id

    with TemporaryDirectory(prefix="lucops-investigation-") as directory:
        snapshot = Path(directory) / "transactions.csv"
        snapshot.write_bytes(payload)
        records = load_csv(snapshot, required_columns=_REQUIRED_COLUMNS)
        if record_index > len(records):
            raise IndexError("Selected record does not exist in the dataset.")
        record = records[record_index - 1]
        validations = run_pipeline(
            snapshot,
            required_columns=_REQUIRED_COLUMNS,
            rules={"valor": is_positive_amount},
            unique_fields=["id_transacao"],
        )
        original_value = _minimize_value("valor", record["valor"])
        add_evidence(
            "transaction",
            "lucops.ingestion.load_csv",
            "valor",
            "Valor do registro selecionado; texto não numérico ou longo é ocultado.",
            original_value,
        )
        inconsistencies = []
        for issue in validations[record_index - 1].issues:
            observed = _minimize_value(issue.field, issue.value)
            evidence_id = add_evidence(
                "quality",
                "lucops.pipeline.run_pipeline",
                issue.field,
                issue.message,
                observed,
                issue.expected,
            )
            inconsistencies.append(
                QualityInconsistency(
                    field=issue.field,
                    message=issue.message,
                    observed_value=observed,
                    expected=issue.expected,
                    evidence_id=evidence_id,
                )
            )
        ml = _ml_information(snapshot, record_index, add_evidence, include_ml)

    limitations = [
        "A investigação abrange apenas o CSV enviado e o registro selecionado.",
        "Não há histórico de clientes, logs da origem ou causa comprovada.",
        "Identificadores pessoais e texto livre são omitidos ou ocultados.",
        "Hashes identificam o CSV, mas não anonimizam os dados.",
        "O detector de ML usa apenas valor; pontuações não são probabilidades nem prova de fraude.",
    ]
    if ml.status == MLStatus.UNAVAILABLE:
        limitations.extend(ml.reasons)
    elif ml.status == MLStatus.INELIGIBLE:
        limitations.append("O registro selecionado não recebeu pontuação de ML.")
    return InvestigationContext(
        schema_version="1",
        dataset_id=dataset_id,
        record_index=record_index,
        transaction=TransactionContext(
            reference=f"{dataset_id}:record:{record_index}",
            original_value=original_value,
        ),
        inconsistencies=tuple(inconsistencies),
        ml=ml,
        evidence=tuple(evidence),
        limitations=tuple(limitations),
    )
