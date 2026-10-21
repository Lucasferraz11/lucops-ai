from sklearn.ensemble import IsolationForest
from sklearn.utils.validation import check_is_fitted

from .schemas import AnomalyAnalysis, AnomalyResult, PreparedTransactions


def analyze_transactions(
    model: IsolationForest,
    transactions: PreparedTransactions,
) -> AnomalyAnalysis:
    """Score eligible transactions using an already fitted in-memory model.

    Positive anomaly scores indicate atypical values relative to the learned
    threshold. Scores are not probabilities or evidence of fraud. No quality
    results are modified and this function never trains the model.
    """
    check_is_fitted(model)
    if not transactions.eligible:
        return AnomalyAnalysis(results=(), ineligible=transactions.ineligible)

    values = [[record.amount] for record in transactions.eligible]
    scores = -model.decision_function(values)
    results = tuple(
        AnomalyResult(
            record_index=record.record_index,
            transaction_id=record.transaction_id,
            original_value=record.original_value,
            anomaly_score=float(score),
            is_anomaly=bool(score > 0),
        )
        for record, score in zip(transactions.eligible, scores, strict=True)
    )
    return AnomalyAnalysis(results=results, ineligible=transactions.ineligible)
