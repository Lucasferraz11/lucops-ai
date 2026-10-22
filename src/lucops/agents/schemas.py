"""Immutable contracts for server-built, minimized investigation contexts."""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Literal


class MLStatus(str, Enum):
    EVALUATED = "evaluated"
    INELIGIBLE = "ineligible"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class TransactionContext:
    reference: str
    original_value: str


@dataclass(frozen=True)
class EvidenceSource:
    dataset_id: str
    # None denotes evidence about the entire current dataset.
    record_index: int | None
    function: str
    field: str


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    kind: Literal["transaction", "quality", "ml"]
    source: EvidenceSource
    description: str
    value: str | float | bool | None
    expected: str | None = None


@dataclass(frozen=True)
class QualityInconsistency:
    field: str
    message: str
    observed_value: str | None
    expected: str | None
    evidence_id: str


@dataclass(frozen=True)
class MLInformation:
    status: MLStatus
    model_version: str | None = None
    anomaly_score: float | None = None
    is_anomaly: bool | None = None
    reasons: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.status, MLStatus):
            raise TypeError("ML status must be an MLStatus value.")
        if self.status == MLStatus.EVALUATED:
            if (
                not isinstance(self.model_version, str)
                or not self.model_version.strip()
                or type(self.anomaly_score) not in (int, float)
                or not math.isfinite(self.anomaly_score)
                or type(self.is_anomaly) is not bool
                or self.is_anomaly != (self.anomaly_score > 0)
                or self.reasons
            ):
                raise ValueError(
                    "Evaluated ML requires a version and consistent finite score."
                )
        elif (
            self.model_version is not None
            or self.anomaly_score is not None
            or self.is_anomaly is not None
            or not self.reasons
        ):
            raise ValueError("Unevaluated ML requires reasons and no prediction.")


@dataclass(frozen=True)
class InvestigationContext:
    schema_version: str
    dataset_id: str
    record_index: int
    transaction: TransactionContext
    inconsistencies: tuple[QualityInconsistency, ...]
    ml: MLInformation
    evidence: tuple[Evidence, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class Hypothesis:
    description: str
    evidence_ids: tuple[str, ...]
    status: Literal["unconfirmed"] = "unconfirmed"


@dataclass(frozen=True)
class Recommendation:
    action: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class InvestigationDraft:
    """Provider output cannot introduce or replace verified evidence."""

    hypotheses: tuple[Hypothesis, ...] = ()
    recommendations: tuple[Recommendation, ...] = ()
    limitations: tuple[str, ...] = ()
    insufficient_evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class InvestigationResult:
    schema_version: str
    mode: str
    provider: str
    context: InvestigationContext
    verified_evidence: tuple[Evidence, ...]
    hypotheses: tuple[Hypothesis, ...]
    recommendations: tuple[Recommendation, ...]
    limitations: tuple[str, ...]
    insufficient_evidence: tuple[str, ...]
    actions_executed: Literal[False] = False
