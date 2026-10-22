"""Read-only orchestration; providers cannot create verified evidence.

Reference validation proves traceability, not the semantic truth of provider
text. Future real providers still require separate semantic evaluation.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from .context import build_investigation_context
from .providers import InvestigationInput, InvestigationProvider, select_provider
from .safety import validate_semantics
from .schemas import (
    Evidence,
    Hypothesis,
    InvestigationDraft,
    InvestigationResult,
    Recommendation,
)
from .tools import (
    find_duplicates,
    get_ml_information,
    get_quality_issues,
    get_transaction,
    prepare_batch,
    summarize_batch,
)


def _collect_evidence(
    dataset_id: str,
    total_records: int,
    groups: tuple[tuple[Evidence, ...], ...],
) -> tuple[Evidence, ...]:
    indexed: dict[str, Evidence] = {}
    for group in groups:
        for item in group:
            if item.source.dataset_id != dataset_id or (
                item.source.record_index is not None
                and not 1 <= item.source.record_index <= total_records
            ):
                raise ValueError(
                    "Evidence origin does not match the investigated dataset."
                )
            if item.evidence_id in indexed and indexed[item.evidence_id] != item:
                raise ValueError("Conflicting verified evidence IDs.")
            indexed[item.evidence_id] = item
    return tuple(indexed.values())


def _validate_draft(draft: InvestigationDraft, evidence: tuple[Evidence, ...]) -> None:
    if type(draft) is not InvestigationDraft:
        raise ValueError("Provider must return an InvestigationDraft.")
    allowed = {item.evidence_id for item in evidence}
    for statements, expected_type in (
        (draft.hypotheses, Hypothesis),
        (draft.recommendations, Recommendation),
    ):
        if type(statements) is not tuple or len(statements) > 20:
            raise ValueError(
                "Provider statements must be tuples with at most 20 items."
            )
        for item in statements:
            if type(item) is not expected_type:
                raise ValueError("Provider statement has an invalid type.")
            text = item.description if isinstance(item, Hypothesis) else item.action
            if not isinstance(text, str) or not text.strip() or len(text) > 2000:
                raise ValueError(
                    "Provider statement must contain bounded nonempty text."
                )
            if isinstance(item, Hypothesis) and item.status != "unconfirmed":
                raise ValueError("Hypotheses must be explicitly unconfirmed.")
            if (
                type(item.evidence_ids) is not tuple
                or not item.evidence_ids
                or any(not isinstance(ref, str) for ref in item.evidence_ids)
                or len(set(item.evidence_ids)) != len(item.evidence_ids)
                or not set(item.evidence_ids) <= allowed
            ):
                raise ValueError(
                    "Provider statement references missing or invalid evidence."
                )
    for texts in (draft.limitations, draft.insufficient_evidence):
        if (
            type(texts) is not tuple
            or len(texts) > 20
            or any(
                not isinstance(text, str) or not text.strip() or len(text) > 2000
                for text in texts
            )
        ):
            raise ValueError("Provider limitations must contain bounded nonempty text.")


def investigate_transaction(
    file_path: str | Path,
    record_index: int,
    *,
    include_ml: bool = True,
    provider: InvestigationProvider | None = None,
    provider_mode: str = "simulated",
) -> InvestigationResult:
    """Investigate one server-owned CSV record with an explicit provider.

    Providers receive only minimized, immutable local results, never filesystem
    paths, personal IDs or raw CSVs. This service never trains or corrects data.
    """
    if type(record_index) is not int or record_index < 1:
        raise ValueError("record_index must be a positive integer.")
    if provider is not None and provider_mode != "simulated":
        raise ValueError("Choose either a provider instance or provider_mode.")
    active_provider = (
        provider if provider is not None else select_provider(provider_mode)
    )
    if (
        not isinstance(active_provider.mode, str)
        or not active_provider.mode.strip()
        or not isinstance(active_provider.name, str)
        or not active_provider.name.strip()
    ):
        raise ValueError("Provider must declare its execution mode and name.")

    # All existing readers see identical bytes, even if the original is changed.
    payload = Path(file_path).read_bytes()
    with TemporaryDirectory(prefix="lucops-agent-") as directory:
        snapshot = Path(directory) / "transactions.csv"
        snapshot.write_bytes(payload)
        context = build_investigation_context(
            snapshot, record_index, include_ml=include_ml
        )
        batch = prepare_batch(snapshot)
    transaction = get_transaction(context)
    quality = get_quality_issues(context)
    ml = get_ml_information(context)
    duplicates = find_duplicates(context, batch)
    summary = summarize_batch(batch)
    tool_results = (transaction, quality, ml, duplicates, summary)
    evidence = _collect_evidence(
        context.dataset_id,
        batch.summary.total_records,
        (context.evidence,) + tuple(result.evidence for result in tool_results),
    )
    provider_input = InvestigationInput(
        context=context,
        evidence=evidence,
        duplicates=duplicates.data,
        batch_summary=summary.data,
    )
    draft = active_provider.generate(provider_input)
    try:
        _validate_draft(draft, evidence)
        validate_semantics(draft, evidence)
    except ValueError as exc:
        if active_provider.mode == "openai":
            from .openai_provider import OpenAIProviderResponseError

            raise OpenAIProviderResponseError(
                "OpenAI returned an invalid investigation."
            ) from exc
        raise
    limitations = (
        context.limitations
        + tuple(text for result in tool_results for text in result.limitations)
        + draft.limitations
    )
    if active_provider.mode == "simulated":
        limitations += (
            "Execução simulada: respostas determinísticas; nenhum LLM foi chamado.",
        )
    insufficient = tuple(
        dict.fromkeys(
            (
                "Não há logs do sistema de origem nem histórico de clientes para confirmar causas.",
                *draft.insufficient_evidence,
            )
        )
    )
    return InvestigationResult(
        schema_version="1",
        mode=active_provider.mode,
        provider=active_provider.name,
        context=context,
        verified_evidence=evidence,
        hypotheses=draft.hypotheses,
        recommendations=draft.recommendations,
        limitations=tuple(dict.fromkeys(limitations)),
        insufficient_evidence=insufficient,
    )
