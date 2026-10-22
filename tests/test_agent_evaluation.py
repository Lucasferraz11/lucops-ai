"""Reproducible semantic checks and a small human-review case corpus."""

import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from sklearn.ensemble import IsolationForest

from lucops.agents.openai_provider import OpenAIProviderError
from lucops.agents.schemas import Hypothesis, InvestigationDraft, Recommendation
from lucops.agents.service import investigate_transaction
from lucops.ml import service as ml_service
from lucops.ml.artifacts import save_model
from lucops.ml.evaluation import make_synthetic_data
from lucops.ml.training import train_detector

CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "agent_review_cases.json").read_text(
        encoding="utf-8"
    )
)
HEADER = "id_transacao,cliente_id,valor,notes\n"


@pytest.fixture(autouse=True)
def no_external_configuration(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LUCOPS_MODEL_PATH", raising=False)
    ml_service._load_cached_model.cache_clear()
    yield
    ml_service._load_cached_model.cache_clear()


def make_csv(tmp_path, rows):
    path = tmp_path / "synthetic.csv"
    path.write_text(HEADER + rows, encoding="utf-8")
    return path


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_review_corpus_matches_server_facts_and_simulated_output(tmp_path, case):
    path = make_csv(tmp_path, case["rows"])
    first = investigate_transaction(
        path, case["record_index"], include_ml=False, provider_mode="simulated"
    )
    second = investigate_transaction(
        path, case["record_index"], include_ml=False, provider_mode="simulated"
    )
    assert first == second
    assert first.mode == "simulated"
    assert {issue.field for issue in first.context.inconsistencies} == set(
        case["quality_fields"]
    )
    assert first.context.ml.status.value == case["ml_status"]
    fragment = case["hypothesis_fragment"]
    if fragment is None:
        assert first.hypotheses == ()
    else:
        assert any(fragment in item.description for item in first.hypotheses)
    facts = {item.evidence_id: item for item in first.verified_evidence}
    assert facts
    for item in (*first.hypotheses, *first.recommendations):
        assert item.evidence_ids
        assert set(item.evidence_ids) <= facts.keys()
    assert all(item.status == "unconfirmed" for item in first.hypotheses)
    assert first.actions_executed is False
    assert "secret@example.com" not in json.dumps(asdict(first))
    assert "ignore previous instructions" not in json.dumps(asdict(first))


def test_valid_ml_alert_is_supported_by_positive_score_evidence(tmp_path, monkeypatch):
    training, _, _ = make_synthetic_data()
    model_path = tmp_path / "trusted.joblib"
    save_model(train_detector(training), model_path, model_version="evaluation-v1")
    monkeypatch.setenv("LUCOPS_MODEL_PATH", str(model_path))
    with patch.object(
        IsolationForest, "fit", side_effect=AssertionError("No retraining")
    ):
        result = investigate_transaction(make_csv(tmp_path, "T3,C1,1000000,note\n"), 1)
    assert result.context.inconsistencies == ()
    assert result.context.ml.status.value == "evaluated"
    assert result.context.ml.is_anomaly is True
    facts = {item.evidence_id: item for item in result.verified_evidence}
    alert = [
        hypothesis
        for hypothesis in result.hypotheses
        if "pode ser atípico" in hypothesis.description
    ]
    assert len(alert) == 1
    assert alert[0].status == "unconfirmed"
    assert any(
        facts[reference].source.field == "is_anomaly" and facts[reference].value is True
        for reference in alert[0].evidence_ids
    )
    assert not any("confirmed" in text for text in result.insufficient_evidence)


@pytest.mark.parametrize(
    "bad_text",
    [
        "Fraud is confirmed.",
        "The confirmed cause is a failed importer.",
        "The customer has previous transaction history.",
        "A statistical anomaly was detected.",
        "Repeated identifiers were detected.",
    ],
)
def test_valid_reference_cannot_support_a_known_false_or_unsupported_claim(
    tmp_path, bad_text
):
    class AdversarialProvider:
        mode = "adversarial-test"
        name = "synthetic-invalid-claim"

        def generate(self, investigation):
            unrelated = investigation.evidence[0].evidence_id
            return InvestigationDraft(
                hypotheses=(Hypothesis(bad_text, (unrelated,)),),
                recommendations=(
                    Recommendation("Review the source value.", (unrelated,)),
                ),
            )

    with pytest.raises(ValueError):
        investigate_transaction(
            make_csv(tmp_path, "T1,C1,100,note\n"),
            1,
            include_ml=False,
            provider=AdversarialProvider(),
        )


def test_recommendation_about_duplicate_must_cite_duplicate_evidence(tmp_path):
    class WrongRecommendation:
        mode = "adversarial-test"
        name = "wrong-recommendation"

        def generate(self, investigation):
            unrelated = investigation.evidence[0].evidence_id
            return InvestigationDraft(
                recommendations=(
                    Recommendation("Review the duplicate records.", (unrelated,)),
                )
            )

    with pytest.raises(ValueError, match="Duplicate claim"):
        investigate_transaction(
            make_csv(tmp_path, "D1,C1,100,note\nD1,C2,200,note\n"),
            1,
            include_ml=False,
            provider=WrongRecommendation(),
        )


def test_simulated_mode_needs_neither_key_nor_network(tmp_path):
    with patch(
        "lucops.agents.openai_provider._make_client",
        side_effect=AssertionError("No external client"),
    ) as external:
        result = investigate_transaction(
            make_csv(tmp_path, "T1,C1,100,note\n"), 1, include_ml=False
        )
    assert result.mode == "simulated"
    external.assert_not_called()


@pytest.mark.parametrize(
    "failure,expected",
    [
        (TimeoutError(), "timed out"),
        (RuntimeError("sensitive network error"), "request failed"),
    ],
)
def test_provider_transport_failure_is_sanitized_and_not_simulated(
    tmp_path, monkeypatch, failure, expected
):
    from lucops.agents import openai_provider

    client = Mock()
    client.responses.create.side_effect = failure
    monkeypatch.setattr(openai_provider, "_make_client", Mock(return_value=client))
    monkeypatch.setattr(openai_provider, "_calls_started", 0)
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.setenv("LUCOPS_AGENT_OPENAI_MAX_CALLS", "1")
    with pytest.raises(OpenAIProviderError, match=expected) as error:
        investigate_transaction(
            make_csv(tmp_path, "T1,C1,100,note\n"),
            1,
            include_ml=False,
            provider_mode="openai",
        )
    assert "sensitive" not in str(error.value)
