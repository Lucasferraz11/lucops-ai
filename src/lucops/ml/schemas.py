from dataclasses import dataclass

from ..core import DataQualityIssue


@dataclass(frozen=True)
class TransactionFeatures:
    record_index: int
    transaction_id: str
    original_value: str
    amount: float


@dataclass(frozen=True)
class IneligibleTransaction:
    record_index: int
    transaction_id: str
    original_value: str
    issues: tuple[DataQualityIssue, ...]


@dataclass(frozen=True)
class PreparedTransactions:
    eligible: tuple[TransactionFeatures, ...]
    ineligible: tuple[IneligibleTransaction, ...]


@dataclass(frozen=True)
class AnomalyResult:
    record_index: int
    transaction_id: str
    original_value: str
    anomaly_score: float
    is_anomaly: bool


@dataclass(frozen=True)
class AnomalyAnalysis:
    results: tuple[AnomalyResult, ...]
    ineligible: tuple[IneligibleTransaction, ...]
