"""Reproducible experiments; synthetic labels do not establish real-world accuracy."""

import json
from collections.abc import Mapping

import numpy as np
import sklearn
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

from .detector import analyze_transactions
from .schemas import PreparedTransactions, TransactionFeatures
from .training import train_detector


def make_synthetic_data(
    seed: int = 42,
) -> tuple[PreparedTransactions, PreparedTransactions, dict[str, bool]]:
    """Generate independent training and evaluation samples with known origins.

    Training: 1000 typical amounts. Evaluation: 200 typical amounts and 20
    controlled extremes. Separate random streams keep evaluation out of training.
    All amounts are positive, finite and rounded to cents.
    """
    train_seed, evaluation_seed = np.random.SeedSequence(seed).spawn(2)
    train_rng = np.random.default_rng(train_seed)
    evaluation_rng = np.random.default_rng(evaluation_seed)
    training_values = np.round(train_rng.lognormal(5, 0.35, 1000), 2)
    typical = np.round(evaluation_rng.lognormal(5, 0.35, 200), 2)
    extremes = np.round(
        np.concatenate(
            (
                evaluation_rng.uniform(1, 5, 10),
                evaluation_rng.uniform(1500, 3000, 10),
            )
        ),
        2,
    )
    evaluation_values = np.concatenate((typical, extremes))
    truth = np.concatenate((np.zeros(200, dtype=bool), np.ones(20, dtype=bool)))
    order = evaluation_rng.permutation(len(evaluation_values))

    def prepare(values, prefix):
        return PreparedTransactions(
            tuple(
                TransactionFeatures(i, f"{prefix}-{i}", f"{value:.2f}", float(value))
                for i, value in enumerate(values, start=1)
            ),
            (),
        )

    training = prepare(training_values, "train")
    evaluation = prepare(evaluation_values[order], "evaluation")
    labels = {
        record.transaction_id: bool(label)
        for record, label in zip(evaluation.eligible, truth[order], strict=True)
    }
    return training, evaluation, labels


def _summarize(scores: np.ndarray, labels: list[bool] | None) -> dict:
    predicted = scores > 0
    summary = {
        "evaluated_records": len(scores),
        "anomalies_detected": int(predicted.sum()),
        "alert_rate": float(predicted.mean()),
        "score_distribution": {
            "min": float(scores.min()),
            "p05": float(np.quantile(scores, 0.05)),
            "median": float(np.median(scores)),
            "p95": float(np.quantile(scores, 0.95)),
            "max": float(scores.max()),
            "mean": float(scores.mean()),
            "std": float(scores.std()),
        },
        "classification_metrics": None,
    }
    if labels is not None:
        precision, recall, f1, _ = precision_recall_fscore_support(
            labels,
            predicted,
            average="binary",
            zero_division=0,
        )
        tn, fp, fn, tp = confusion_matrix(
            labels, predicted, labels=[False, True]
        ).ravel()
        summary["classification_metrics"] = {
            "precision": float(precision),
            "recall": float(recall),
            "f1": float(f1),
            "true_negatives": int(tn),
            "false_positives": int(fp),
            "false_negatives": int(fn),
            "true_positives": int(tp),
            "positive_labels": int(sum(labels)),
            "zero_division": 0,
        }
    return summary


def evaluate_detector(
    training: PreparedTransactions,
    evaluation: PreparedTransactions,
    labels: Mapping[str, bool] | None = None,
    *,
    lower_quantile: float = 0.01,
    upper_quantile: float = 0.99,
) -> dict:
    """Train once and evaluate fixed settings on a separate held-out dataset.

    Labels must map every eligible evaluation ID to a real boolean, with no
    extras. They are never passed to training or threshold selection.
    Quantiles must be chosen before inspecting evaluation results.
    Scores from the two methods have different units and cannot be compared.
    """
    if not 0 <= lower_quantile < upper_quantile <= 1:
        raise ValueError("Quantiles must satisfy 0 <= lower < upper <= 1.")
    if not evaluation.eligible:
        raise ValueError("Evaluation requires at least one eligible transaction.")
    train_ids = [r.transaction_id for r in training.eligible]
    evaluation_ids = [r.transaction_id for r in evaluation.eligible]
    if len(set(train_ids)) != len(train_ids) or len(set(evaluation_ids)) != len(
        evaluation_ids
    ):
        raise ValueError("Training and evaluation require unique transaction IDs.")
    if set(train_ids) & set(evaluation_ids):
        raise ValueError("Training and evaluation transaction IDs must be disjoint.")
    aligned_labels = None
    if labels is not None:
        if set(labels) != set(evaluation_ids) or any(
            type(v) is not bool for v in labels.values()
        ):
            raise ValueError(
                "Labels must map exactly the eligible evaluation IDs to booleans."
            )
        aligned_labels = [labels[transaction_id] for transaction_id in evaluation_ids]

    model = train_detector(training)
    analysis = analyze_transactions(model, evaluation)
    model_scores = np.array([r.anomaly_score for r in analysis.results])
    training_values = np.array([r.amount for r in training.eligible])
    lower, upper = np.quantile(training_values, [lower_quantile, upper_quantile])
    evaluation_values = np.array([r.amount for r in evaluation.eligible])
    baseline_scores = np.maximum(lower - evaluation_values, evaluation_values - upper)
    return {
        "sklearn_version": sklearn.__version__,
        "numpy_version": np.__version__,
        "training_records": len(training.eligible),
        "training_skipped_records": len(training.ineligible),
        "evaluation_skipped_records": len(evaluation.ineligible),
        "model_parameters": model.get_params(),
        "isolation_forest": _summarize(model_scores, aligned_labels),
        "quantile_baseline": {
            "lower_quantile": lower_quantile,
            "upper_quantile": upper_quantile,
            "lower_bound": float(lower),
            "upper_bound": float(upper),
            **_summarize(baseline_scores, aligned_labels),
        },
    }


def main() -> None:
    """Print the fixed synthetic experiment; no artifact files are generated."""
    training, evaluation, labels = make_synthetic_data()
    report = evaluate_detector(training, evaluation, labels)
    report["synthetic_seed"] = 42
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
