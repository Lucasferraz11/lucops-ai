from sklearn.ensemble import IsolationForest

from .schemas import PreparedTransactions


def train_detector(transactions: PreparedTransactions) -> IsolationForest:
    """Fit a reproducible model on eligible amounts only.

    At least two eligible transactions are required. The caller retains the
    rejected records in transactions.ineligible. Training is always explicit.
    """
    if len(transactions.eligible) < 2:
        raise ValueError("Training requires at least two eligible transactions.")

    model = IsolationForest(
        n_estimators=100,
        max_samples="auto",
        contamination="auto",
        random_state=42,
    )
    model.fit([[record.amount] for record in transactions.eligible])
    model.training_record_count_ = len(transactions.eligible)
    return model
