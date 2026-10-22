"""Deterministic, read-only investigation tools for server-owned data.

Context queries do not read files or run ML. Prepare a batch once to reuse
duplicate indexing and statistics. The derived snapshot contains no raw IDs,
client identifiers, or free text. It must match the context's exact CSV hash.
No historical statistics, root-cause conclusions, or fraud claims are inferred.
"""

import hashlib
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Generic, Literal, TypeVar

from ..ingestion import load_csv
from ..rules import is_positive_amount
from .schemas import (
    Evidence,
    EvidenceSource,
    InvestigationContext,
    MLInformation,
    QualityInconsistency,
    TransactionContext,
)

T = TypeVar("T")
_REQUIRED_COLUMNS = ("id_transacao", "cliente_id", "valor")
# Statistics deliberately use bounded values to avoid overflow/huge outputs.
_MAX_STAT_AMOUNT = Decimal("3.4028234663852886e38")
_AMOUNT_RULE = (
    "Apenas CSV atual: valor não vazio, até 64 caracteres, aprovado por "
    "is_positive_amount e até 3.4028234663852886e38. Outras inconsistências "
    "não excluem o valor; duplicados são incluídos. Média e mediana são "
    "arredondadas aos centavos com ROUND_HALF_EVEN."
)


@dataclass(frozen=True)
class ToolResult(Generic[T]):
    tool: str
    dataset_id: str
    record_index: int | None
    data: T
    evidence: tuple[Evidence, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class AmountStatistics:
    included_records: int
    excluded_records: int
    minimum: str | None
    maximum: str | None
    mean: str | None
    median: str | None
    inclusion_rule: str = _AMOUNT_RULE


@dataclass(frozen=True)
class BatchSummary:
    total_records: int
    missing_transaction_ids: int
    missing_client_ids: int
    missing_amounts: int
    duplicate_id_groups: int
    repeated_id_records: int
    amounts: AmountStatistics
    scope: str = "current_csv"


@dataclass(frozen=True)
class BatchSnapshot:
    """Internal derived data. Prepare once; never accept from a browser.

    Group numbers are local aliases, not original transaction identifiers.
    The source file and all raw fields are discarded after preparation.
    """

    dataset_id: str
    record_groups: tuple[int | None, ...]
    identifier_groups: tuple[tuple[int, ...], ...]
    summary: BatchSummary


@dataclass(frozen=True)
class DuplicateMatches:
    identifier_present: bool
    related_record_indices: tuple[int, ...]


def _amount_statistics(values: list[Decimal], total: int) -> AmountStatistics:
    if not values:
        return AmountStatistics(0, total, None, None, None, None)
    ordered = sorted(values)
    count = len(ordered)
    with localcontext() as decimal_context:
        decimal_context.prec = 50 + len(str(count))
        decimal_context.rounding = ROUND_HALF_EVEN
        mean = sum(ordered, Decimal(0)) / count
        midpoint = count // 2
        median = (
            ordered[midpoint]
            if count % 2
            else (ordered[midpoint - 1] + ordered[midpoint]) / 2
        )
        return AmountStatistics(
            count,
            total - count,
            f"{ordered[0]:.2f}",
            f"{ordered[-1]:.2f}",
            f"{mean:.2f}",
            f"{median:.2f}",
        )


def prepare_batch(file_path: str | Path) -> BatchSnapshot:
    """Read a server-owned CSV once and compute reusable, minimized batch data.

    Missing identifiers are excluded from duplicate matching, as in the
    existing pipeline. Nonempty IDs match exactly, without normalization.
    This is not a public API for arbitrary client-supplied filesystem paths.
    """
    payload = Path(file_path).read_bytes()
    dataset_id = "sha256:" + hashlib.sha256(payload).hexdigest()
    with TemporaryDirectory(prefix="lucops-tools-") as directory:
        snapshot = Path(directory) / "transactions.csv"
        snapshot.write_bytes(payload)
        records = load_csv(snapshot, required_columns=_REQUIRED_COLUMNS)

    identifiers: dict[str, int] = {}
    groups: list[list[int]] = []
    record_groups: list[int | None] = []
    values: list[Decimal] = []
    missing_ids = missing_clients = missing_amounts = 0
    for index, record in enumerate(records, start=1):
        identifier = record["id_transacao"]
        if identifier == "":
            missing_ids += 1
            record_groups.append(None)
        else:
            if identifier not in identifiers:
                identifiers[identifier] = len(groups)
                groups.append([])
            group = identifiers[identifier]
            groups[group].append(index)
            record_groups.append(group)
        missing_clients += record["cliente_id"] == ""
        amount = record["valor"]
        missing_amounts += amount == ""
        if amount and len(amount) <= 64 and is_positive_amount(amount):
            numeric = Decimal(amount)
            if numeric <= _MAX_STAT_AMOUNT:
                values.append(numeric)

    duplicate_groups = [group for group in groups if len(group) > 1]
    summary = BatchSummary(
        total_records=len(records),
        missing_transaction_ids=missing_ids,
        missing_client_ids=missing_clients,
        missing_amounts=missing_amounts,
        duplicate_id_groups=len(duplicate_groups),
        repeated_id_records=sum(len(group) - 1 for group in duplicate_groups),
        amounts=_amount_statistics(values, len(records)),
    )
    return BatchSnapshot(
        dataset_id,
        tuple(record_groups),
        tuple(tuple(group) for group in groups),
        summary,
    )


def _context_evidence(
    context: InvestigationContext,
    evidence_ids: tuple[str, ...],
) -> tuple[Evidence, ...]:
    indexed = {item.evidence_id: item for item in context.evidence}
    if len(indexed) != len(context.evidence):
        raise ValueError("Context contains duplicate evidence IDs.")
    try:
        selected = tuple(indexed[identifier] for identifier in evidence_ids)
    except KeyError as exc:
        raise ValueError("Context contains an unresolved evidence reference.") from exc
    if any(
        item.source.dataset_id != context.dataset_id
        or item.source.record_index != context.record_index
        for item in selected
    ):
        raise ValueError("Context evidence does not match the selected record.")
    return selected


def _evidence(
    dataset_id: str,
    record_index: int | None,
    tool: str,
    field: str,
    description: str,
    value: str | float | bool | None,
    *,
    kind: Literal["transaction", "quality", "ml"] = "transaction",
) -> Evidence:
    scope = "batch" if record_index is None else f"record:{record_index}"
    return Evidence(
        evidence_id=f"{dataset_id}:{scope}:tool:{tool}:{field}",
        kind=kind,
        source=EvidenceSource(
            dataset_id,
            record_index,
            f"lucops.agents.tools.{tool}",
            field,
        ),
        description=description,
        value=value,
    )


def get_transaction(context: InvestigationContext) -> ToolResult[TransactionContext]:
    """Return only the selected transaction fields already minimized in context."""
    evidence = _context_evidence(
        context,
        tuple(e.evidence_id for e in context.evidence if e.kind == "transaction"),
    )
    return ToolResult(
        "get_transaction",
        context.dataset_id,
        context.record_index,
        context.transaction,
        evidence,
        context.limitations,
    )


def get_quality_issues(
    context: InvestigationContext,
) -> ToolResult[tuple[QualityInconsistency, ...]]:
    """Return existing findings and expectations without recalculating quality."""
    evidence = _context_evidence(
        context,
        tuple(issue.evidence_id for issue in context.inconsistencies),
    )
    count_evidence = _evidence(
        context.dataset_id,
        context.record_index,
        "get_quality_issues",
        "inconsistency_count",
        "Inconsistências de qualidade já verificadas no contexto.",
        str(len(context.inconsistencies)),
        kind="quality",
    )
    return ToolResult(
        "get_quality_issues",
        context.dataset_id,
        context.record_index,
        context.inconsistencies,
        evidence + (count_evidence,),
        context.limitations,
    )


def get_ml_information(context: InvestigationContext) -> ToolResult[MLInformation]:
    """Return existing ML status and results, never invoke inference or training."""
    evidence = _context_evidence(context, context.ml.evidence_ids)
    status_evidence = _evidence(
        context.dataset_id,
        context.record_index,
        "get_ml_information",
        "ml.status",
        "Situação de ML registrada no servidor; ausência não é previsão negativa.",
        context.ml.status.value,
        kind="ml",
    )
    return ToolResult(
        "get_ml_information",
        context.dataset_id,
        context.record_index,
        context.ml,
        evidence + (status_evidence,),
        context.limitations,
    )


def find_duplicates(
    context: InvestigationContext,
    batch: BatchSnapshot,
) -> ToolResult[DuplicateMatches]:
    """Locate other matching IDs, including the first occurrence, without exposing IDs."""
    if context.dataset_id != batch.dataset_id:
        raise ValueError("Batch snapshot does not match the context dataset.")
    if not 1 <= context.record_index <= batch.summary.total_records:
        raise ValueError("Selected record is outside the batch snapshot.")
    group = batch.record_groups[context.record_index - 1]
    peers = (
        tuple(i for i in batch.identifier_groups[group] if i != context.record_index)
        if group is not None
        else ()
    )
    presence = _evidence(
        context.dataset_id,
        context.record_index,
        "find_duplicates",
        "identifier_present",
        "Indica se o ID selecionado não está vazio no CSV atual.",
        group is not None,
    )
    related = tuple(
        Evidence(
            evidence_id=f"{context.transaction.reference}:tool:find_duplicates:peer:{index}",
            kind="quality",
            source=EvidenceSource(
                batch.dataset_id,
                index,
                "lucops.agents.tools.find_duplicates",
                "id_transacao",
            ),
            description="Este registro do CSV atual compartilha o ID selecionado.",
            value=str(index),
            expected="unique value",
        )
        for index in peers
    )
    count = _evidence(
        context.dataset_id,
        context.record_index,
        "find_duplicates",
        "related_record_count",
        "Outros registros com o mesmo ID neste CSV, exceto o selecionado.",
        str(len(peers)),
        kind="quality",
    )
    return ToolResult(
        "find_duplicates",
        context.dataset_id,
        context.record_index,
        DuplicateMatches(group is not None, peers),
        (presence, count) + related,
        (
            "Somente o CSV atual; IDs vazios não são comparados.",
            "IDs são comparados exatamente, incluindo espaços e maiúsculas.",
            "Um ID compartilhado não confirma causa nem fraude.",
        ),
    )


def summarize_batch(batch: BatchSnapshot) -> ToolResult[BatchSummary]:
    """Return cached current-CSV counts/statistics; no history or ML aggregation."""
    summary = batch.summary
    fields = {
        "total_records": summary.total_records,
        "missing_transaction_ids": summary.missing_transaction_ids,
        "missing_client_ids": summary.missing_client_ids,
        "missing_amounts": summary.missing_amounts,
        "duplicate_id_groups": summary.duplicate_id_groups,
        "repeated_id_records": summary.repeated_id_records,
        "amounts.included_records": summary.amounts.included_records,
        "amounts.excluded_records": summary.amounts.excluded_records,
        "amounts.minimum": summary.amounts.minimum,
        "amounts.maximum": summary.amounts.maximum,
        "amounts.mean": summary.amounts.mean,
        "amounts.median": summary.amounts.median,
    }
    evidence = tuple(
        _evidence(
            batch.dataset_id,
            None,
            "summarize_batch",
            field,
            f"Calculado apenas a partir do CSV atual: {field}.",
            str(value) if type(value) is int else value,
        )
        for field, value in fields.items()
    )
    return ToolResult(
        "summarize_batch",
        batch.dataset_id,
        None,
        summary,
        evidence,
        (
            "Estatísticas do CSV atual, não históricas nem específicas de clientes.",
            _AMOUNT_RULE,
            "Essas contagens não substituem as métricas tradicionais de qualidade.",
        ),
    )
