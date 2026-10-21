from unittest.mock import patch

import numpy as np
import pytest
from sklearn.ensemble import IsolationForest
from sklearn.exceptions import NotFittedError

from lucops.ml.detector import analyze_transactions
from lucops.ml.features import prepare_csv_features
from lucops.ml.schemas import PreparedTransactions, TransactionFeatures
from lucops.ml.training import train_detector
from lucops.pipeline import run_pipeline
from lucops.rules import is_positive_amount
from lucops.status import get_quality_status
from lucops.summary import summarize_results


def prepared(amounts):
    return PreparedTransactions(
        eligible=tuple(
            TransactionFeatures(i, f"T{i}", str(amount), float(amount))
            for i, amount in enumerate(amounts, start=1)
        ),
        ineligible=(),
    )


@pytest.fixture
def training_data():
    return prepared(range(100, 301))


def test_training_is_reproducible(training_data):
    first = train_detector(training_data)
    second = train_detector(training_data)
    values = [[150.0], [200.0], [1000000.0]]
    assert first.random_state == 42
    assert first.n_features_in_ == 1
    np.testing.assert_array_equal(
        first.decision_function(values), second.decision_function(values)
    )


@pytest.mark.parametrize("amounts", [[], [100]])
def test_training_requires_two_eligible_records(amounts):
    with pytest.raises(ValueError, match="at least two eligible"):
        train_detector(prepared(amounts))


def test_scores_new_transactions_without_training(training_data):
    model = train_detector(training_data)
    new_data = prepared([200, 1000000])
    with patch.object(model, "fit", side_effect=AssertionError("Unexpected training")):
        result = analyze_transactions(model, new_data)
        repeated = analyze_transactions(model, new_data)
    assert result == repeated
    typical, atypical = result.results
    assert typical.transaction_id == "T1"
    assert typical.record_index == 1
    assert typical.original_value == "200"
    assert not typical.is_anomaly
    assert atypical.is_anomaly
    assert atypical.anomaly_score > typical.anomaly_score
    assert isinstance(atypical.anomaly_score, float)
    np.testing.assert_allclose(
        [record.anomaly_score for record in result.results],
        -model.decision_function([[200], [1000000]]),
    )
    assert [record.is_anomaly for record in result.results] == [
        label == -1 for label in model.predict([[200], [1000000]])
    ]


@pytest.mark.parametrize("amounts", [[], [200]])
def test_unfitted_model_is_rejected_even_for_empty_input(amounts):
    with pytest.raises(NotFittedError):
        analyze_transactions(IsolationForest(), prepared(amounts))


def test_empty_analysis_returns_empty_results(training_data):
    result = analyze_transactions(train_detector(training_data), prepared([]))
    assert result.results == result.ineligible == ()


def test_ineligible_records_are_skipped_with_reasons(tmp_path):
    path = tmp_path / "transactions.csv"
    path.write_text(
        "id_transacao,cliente_id,valor\n"
        "A,C1,100.00\nB,C2,200.00\nA,,-1.00\nD,C4,300.00\n",
        encoding="utf-8",
    )
    data = prepare_csv_features(path)
    model = train_detector(data)
    reference = train_detector(PreparedTransactions(data.eligible, ()))
    np.testing.assert_array_equal(
        model.decision_function([[150]]), reference.decision_function([[150]])
    )
    result = analyze_transactions(model, data)
    assert [record.record_index for record in result.results] == [1, 2, 4]
    assert result.ineligible == data.ineligible
    assert len(result.ineligible[0].issues) == 3
    only_ineligible = PreparedTransactions((), data.ineligible)
    assert analyze_transactions(model, only_ineligible).ineligible == data.ineligible
    with pytest.raises(ValueError, match="at least two eligible"):
        train_detector(only_ineligible)


def test_anomalies_do_not_change_quality_status(tmp_path, training_data):
    path = tmp_path / "new.csv"
    path.write_text(
        "id_transacao,cliente_id,valor\nNEW,C1,1000000.00\n",
        encoding="utf-8",
    )
    before = path.read_bytes()
    data = prepare_csv_features(path)
    result = analyze_transactions(train_detector(training_data), data)
    assert result.results[0].is_anomaly
    quality = run_pipeline(
        path,
        ["id_transacao", "cliente_id", "valor"],
        rules={"valor": is_positive_amount},
        unique_fields=["id_transacao"],
    )
    assert get_quality_status(summarize_results(quality)) == "SEM INCONSIST\u00caNCIAS"
    assert path.read_bytes() == before


def test_zero_score_is_not_an_anomaly(training_data):
    model = train_detector(training_data)
    with patch.object(model, "decision_function", return_value=np.array([0.0])):
        result = analyze_transactions(model, prepared([200]))
    assert result.results[0].anomaly_score == 0.0
    assert not result.results[0].is_anomaly
