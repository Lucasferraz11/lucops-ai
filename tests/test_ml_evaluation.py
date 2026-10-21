import json
from unittest.mock import patch

import numpy as np
import pytest

from lucops.core import DataQualityIssue
from lucops.ml.evaluation import (
    _summarize,
    evaluate_detector,
    main,
    make_synthetic_data,
)
from lucops.ml.schemas import (
    IneligibleTransaction,
    PreparedTransactions,
    TransactionFeatures,
)
from lucops.ml.training import train_detector
from lucops.rules import is_positive_amount


def prepared(values, prefix):
    return PreparedTransactions(
        tuple(
            TransactionFeatures(i, f"{prefix}-{i}", str(value), float(value))
            for i, value in enumerate(values, start=1)
        ),
        (),
    )


@pytest.fixture
def small_data():
    return prepared([100, 150, 200, 250], "train"), prepared([150, 1000], "eval")


def test_synthetic_generation_is_reproducible_and_separate():
    first = make_synthetic_data()
    assert first == make_synthetic_data()
    assert first != make_synthetic_data(43)
    training, evaluation, labels = first
    assert len(training.eligible) == 1000
    assert len(evaluation.eligible) == 220
    assert sum(labels.values()) == 20
    assert not (
        {r.transaction_id for r in training.eligible}
        & {r.transaction_id for r in evaluation.eligible}
    )
    assert all(is_positive_amount(r.original_value) for r in training.eligible)
    assert all(is_positive_amount(r.original_value) for r in evaluation.eligible)
    assert all(
        (r.amount < 5 or r.amount > 1500)
        for r in evaluation.eligible
        if labels[r.transaction_id]
    )


def test_experiment_is_reproducible():
    training, evaluation, labels = make_synthetic_data()
    first = evaluate_detector(training, evaluation, labels)
    second = evaluate_detector(training, evaluation, labels)
    assert first == second
    assert first["training_records"] == 1000
    for method in ("isolation_forest", "quantile_baseline"):
        summary = first[method]
        assert summary["evaluated_records"] == 220
        assert summary["classification_metrics"]["true_positives"] == 20
        assert summary["alert_rate"] == summary["anomalies_detected"] / 220
        distribution = summary["score_distribution"]
        assert (
            distribution["min"]
            <= distribution["p05"]
            <= distribution["median"]
            <= distribution["p95"]
            <= distribution["max"]
        )
        assert distribution["std"] >= 0
    json.dumps(first, allow_nan=False)


def test_training_and_quantiles_never_use_evaluation_or_labels(small_data):
    training, evaluation = small_data
    with patch("lucops.ml.evaluation.train_detector", wraps=train_detector) as train:
        report = evaluate_detector(
            training,
            evaluation,
            {"eval-2": True, "eval-1": False},
        )
    train.assert_called_once_with(training)
    expected = np.quantile([100, 150, 200, 250], [0.01, 0.99])
    assert report["quantile_baseline"]["lower_bound"] == expected[0]
    assert report["quantile_baseline"]["upper_bound"] == expected[1]
    changed = evaluate_detector(
        training,
        prepared([1000000, 2000000], "other"),
        {"other-1": False, "other-2": True},
    )
    assert changed["model_parameters"] == report["model_parameters"]
    assert changed["quantile_baseline"]["lower_bound"] == expected[0]
    assert changed["quantile_baseline"]["upper_bound"] == expected[1]


def test_labels_are_optional_and_do_not_affect_scores(small_data):
    training, evaluation = small_data
    unlabeled = evaluate_detector(training, evaluation)
    labeled = evaluate_detector(training, evaluation, {"eval-1": False, "eval-2": True})
    for method in ("isolation_forest", "quantile_baseline"):
        assert unlabeled[method]["classification_metrics"] is None
        assert (
            unlabeled[method]["score_distribution"]
            == labeled[method]["score_distribution"]
        )


def test_metrics_match_known_confusion_matrix():
    # Predictions: positive, positive, negative, negative.
    summary = _summarize(np.array([0.2, 0.1, -0.1, 0.0]), [True, False, True, False])
    metrics = summary["classification_metrics"]
    assert metrics["precision"] == metrics["recall"] == metrics["f1"] == 0.5
    assert [
        metrics[name]
        for name in (
            "true_negatives",
            "false_positives",
            "false_negatives",
            "true_positives",
        )
    ] == [1, 1, 1, 1]
    assert summary["alert_rate"] == 0.5


def test_undefined_metrics_use_documented_zero_convention():
    metrics = _summarize(np.array([-1.0, -2.0]), [False, False])[
        "classification_metrics"
    ]
    assert metrics["precision"] == metrics["recall"] == metrics["f1"] == 0
    assert metrics["positive_labels"] == 0
    assert metrics["zero_division"] == 0


@pytest.mark.parametrize(
    "labels",
    [
        {},
        {"eval-1": False},
        {"eval-1": False, "eval-2": True, "extra": False},
        {"eval-1": 0, "eval-2": 1},
        {"eval-1": False, "eval-2": None},
    ],
)
def test_invalid_or_misaligned_labels_are_rejected_before_training(small_data, labels):
    with patch("lucops.ml.evaluation.train_detector") as train:
        with pytest.raises(ValueError, match="Labels"):
            evaluate_detector(*small_data, labels)
        train.assert_not_called()


@pytest.mark.parametrize(
    "lower,upper",
    [
        (-0.1, 0.99),
        (0.1, 1.1),
        (0.5, 0.5),
        (0.9, 0.1),
        (float("nan"), 1),
    ],
)
def test_invalid_quantiles_are_rejected(small_data, lower, upper):
    with pytest.raises(ValueError, match="Quantiles"):
        evaluate_detector(*small_data, lower_quantile=lower, upper_quantile=upper)


def test_empty_evaluation_and_insufficient_training(small_data):
    training, evaluation = small_data
    with pytest.raises(ValueError, match="Evaluation requires"):
        evaluate_detector(training, prepared([], "empty"))
    with pytest.raises(ValueError, match="at least two"):
        evaluate_detector(prepared([100], "train"), evaluation)


def test_overlapping_or_duplicate_ids_are_rejected(small_data):
    training, evaluation = small_data
    with pytest.raises(ValueError, match="disjoint"):
        evaluate_detector(training, training)
    duplicated = PreparedTransactions(evaluation.eligible * 2, ())
    with pytest.raises(ValueError, match="unique"):
        evaluate_detector(training, duplicated)


def test_ineligible_records_are_excluded_and_counted(small_data):
    training, evaluation = small_data
    rejected = IneligibleTransaction(
        10,
        "bad",
        "-1",
        (DataQualityIssue("valor", "Rule failed.", "-1"),),
    )
    with_rejected = PreparedTransactions(training.eligible, (rejected,))
    evaluation_with_rejected = PreparedTransactions(evaluation.eligible, (rejected,))
    original = evaluate_detector(training, evaluation)
    report = evaluate_detector(with_rejected, evaluation_with_rejected)
    assert (
        report["training_skipped_records"] == report["evaluation_skipped_records"] == 1
    )
    assert report["isolation_forest"] == original["isolation_forest"]
    assert report["quantile_baseline"] == original["quantile_baseline"]


def test_module_prints_serializable_report(capsys):
    main()
    report = json.loads(capsys.readouterr().out)
    assert report["synthetic_seed"] == 42
    assert report["isolation_forest"]["evaluated_records"] == 220
