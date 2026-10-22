"""Conservative checks for mechanically identifiable unsupported claims."""

import re

from .schemas import Evidence, InvestigationDraft

_UNSUPPORTED_FACT = re.compile(
    r"\b(?:fraud|fraude)\s+(?:is|was|has been|é|foi|confirmed|comprovad[ao])\b"
    r"|\b(?:confirmed|proven|comprovad[ao])\s+(?:root\s+)?(?:cause|causa)\b"
    r"|\b(?:customer|client|cliente)\s+(?:has|had|possui|tem)\b.{0,80}"
    r"\b(?:history|hist[oó]rico|previous|prior|anteriores)\b",
    re.IGNORECASE,
)
_DUPLICATE = re.compile(
    r"\b(?:duplicat\w*|repeated identifiers?|identificadores? repetidos?)\b",
    re.IGNORECASE,
)
_ALERT = re.compile(
    r"\b(?:anomal\w*|statistical alert|alerta estatístico)\b", re.IGNORECASE
)


def validate_semantics(
    draft: InvestigationDraft, evidence: tuple[Evidence, ...]
) -> None:
    """Reject explicit false claims; this is not a semantic truth oracle."""
    by_id = {item.evidence_id: item for item in evidence}
    for text in (*draft.limitations, *draft.insufficient_evidence):
        if _UNSUPPORTED_FACT.search(text):
            raise ValueError("Provider states an unsupported verified fact.")
    for statement in (*draft.hypotheses, *draft.recommendations):
        text = (
            statement.description
            if hasattr(statement, "description")
            else statement.action
        )
        if _UNSUPPORTED_FACT.search(text):
            raise ValueError("Provider states an unsupported verified fact.")
        cited = tuple(by_id[identifier] for identifier in statement.evidence_ids)
        if _DUPLICATE.search(text) and not any(
            item.source.function == "lucops.agents.tools.find_duplicates"
            and item.source.field == "id_transacao"
            for item in cited
        ):
            raise ValueError("Duplicate claim lacks duplicate-record evidence.")
        if _ALERT.search(text) and not any(
            item.source.field == "is_anomaly" and item.value is True for item in cited
        ):
            raise ValueError("Anomaly claim lacks a positive ML alert.")
