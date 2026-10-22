from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from lucops.agents.openai_provider import (
    OpenAIProviderError,
    OpenAIProviderResponseError,
)
from lucops.agents.schemas import Hypothesis, InvestigationDraft
from lucops.api import app
from lucops.ml import service as ml_service
from lucops.ml.artifacts import save_model
from lucops.ml.evaluation import make_synthetic_data
from lucops.ml.training import train_detector

client = TestClient(app)
HEADER = b"id_transacao,cliente_id,valor\n"


@pytest.fixture(autouse=True)
def isolate_config(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LUCOPS_MODEL_PATH", raising=False)
    ml_service._load_cached_model.cache_clear()
    yield
    ml_service._load_cached_model.cache_clear()


def investigate(rows, index=1, provider=None):
    data = {"record_index": str(index)}
    if provider is not None:
        data["provider"] = provider
    return client.post(
        "/investigations",
        files={"file": ("sample.csv", HEADER + rows, "text/csv")},
        data=data,
    )


def test_invalid_transaction_returns_grounded_simulated_result():
    response = investigate(b"T1,C1,-20\n")
    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "simulated"
    assert result["context"]["record_index"] == 1
    assert result["context"]["ml"]["status"] == "ineligible"
    assert result["hypotheses"][0]["status"] == "unconfirmed"
    facts = {item["evidence_id"] for item in result["verified_evidence"]}
    assert all(set(item["evidence_ids"]) <= facts for item in result["hypotheses"])
    assert result["actions_executed"] is False
    assert "T1" not in str(result)


def test_duplicate_first_record_uses_index_and_peer_evidence():
    result = investigate(b"D1,C1,100\nD1,C2,200\n").json()
    assert result["context"]["inconsistencies"] == []
    assert result["context"]["record_index"] == 1
    assert any(
        "Identificadores repetidos" in h["description"] for h in result["hypotheses"]
    )
    assert any(
        item["source"]["record_index"] == 2
        and item["source"]["field"] == "id_transacao"
        for item in result["verified_evidence"]
    )


def test_normal_record_reports_ml_unavailable_without_false_negative():
    result = investigate(b"T2,C2,100\n").json()
    assert result["context"]["inconsistencies"] == []
    assert result["context"]["ml"]["status"] == "unavailable"
    assert result["context"]["ml"]["is_anomaly"] is None
    assert result["hypotheses"] == []


def test_valid_statistical_alert_uses_pretrained_model(tmp_path, monkeypatch):
    training, _, _ = make_synthetic_data()
    artifact = tmp_path / "trusted.joblib"
    save_model(train_detector(training), artifact)
    monkeypatch.setenv("LUCOPS_MODEL_PATH", str(artifact))
    result = investigate(b"T3,C3,1000000\n").json()
    assert result["context"]["inconsistencies"] == []
    assert result["context"]["ml"]["is_anomaly"] is True
    assert any("pode ser atípico" in h["description"] for h in result["hypotheses"])


@pytest.mark.parametrize(
    "body", [b"wrong\nvalue\n", b"id_transacao,valor\nT1,10\n", b""]
)
def test_invalid_csv_returns_400(body):
    response = client.post(
        "/investigations",
        files={"file": ("bad.csv", body, "text/csv")},
        data={"record_index": "1"},
    )
    assert response.status_code == 400


def test_missing_and_invalid_index():
    assert investigate(b"T1,C1,100\n", index=2).status_code == 404
    assert investigate(b"T1,C1,100\n", index=0).status_code == 422
    response = client.post(
        "/investigations", files={"file": ("sample.csv", HEADER, "text/csv")}
    )
    assert response.status_code == 422


def test_openai_without_key_returns_503_and_never_calls_client():
    with patch(
        "lucops.agents.openai_provider._make_client",
        side_effect=AssertionError("No client without key"),
    ):
        response = investigate(b"T1,C1,100\n", provider="openai")
    assert response.status_code == 503
    assert response.json()["detail"] == "Provedor de investigação indisponível."


def test_openai_provider_failure_does_not_fall_back():
    with patch(
        "lucops.agents.openai_provider.OpenAIProvider.generate",
        side_effect=OpenAIProviderError("OpenAI request failed."),
    ):
        response = investigate(b"T1,C1,100\n", provider="openai")
    assert response.status_code == 503
    assert response.json()["detail"] == "Provedor de investigação indisponível."


def test_invalid_openai_model_is_not_classified_as_invalid_csv(monkeypatch):
    monkeypatch.setenv("LUCOPS_AGENT_OPENAI_MODEL", "invalid model")
    response = investigate(b"T1,C1,100\n", provider="openai")
    assert response.status_code == 503
    assert response.json()["detail"] == "Provedor de investigação indisponível."
    assert investigate(b"T1,C1,100\n", index=2, provider="openai").status_code == 404


def test_provider_response_failure_is_502_without_sensitive_details():
    with patch(
        "lucops.agents.openai_provider.OpenAIProvider.generate",
        side_effect=OpenAIProviderResponseError("secret provider payload"),
    ):
        response = investigate(b"T1,C1,100\n", provider="openai")
    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Resposta do provedor de investigação inválida."
    )
    assert "secret" not in response.text
    assert "simulated" not in response.text


def test_invalid_provider_draft_is_502_without_fallback():
    draft = InvestigationDraft(
        hypotheses=(Hypothesis("Talvez haja um problema.", ("missing",)),)
    )
    with patch(
        "lucops.agents.openai_provider.OpenAIProvider.generate", return_value=draft
    ):
        response = investigate(b"T1,C1,100\n", provider="openai")
    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Resposta do provedor de investigação inválida."
    )


def test_internal_value_error_is_500_without_sensitive_details():
    with patch(
        "lucops.agents.service.investigate_transaction",
        side_effect=ValueError("secret internal detail"),
    ):
        response = investigate(b"T1,C1,100\n")
    assert response.status_code == 500
    assert response.json()["detail"] == "Falha interna na investigação."
    assert "secret" not in response.text


def test_openai_call_limit_zero_blocks_outbound_request(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "mock-only-key")
    monkeypatch.setenv("LUCOPS_AGENT_OPENAI_MAX_CALLS", "0")
    fake_client = Mock()
    with patch("lucops.agents.openai_provider._make_client", return_value=fake_client):
        response = investigate(b"T1,C1,100\n", provider="openai")
    assert response.status_code == 503
    fake_client.responses.create.assert_not_called()


def test_invalid_provider_rejected_and_existing_contracts_still_respond():
    assert investigate(b"T1,C1,100\n", provider="other").status_code == 422
    assert client.get("/health").json() == {"status": "ok", "service": "LucOps AI"}
    assert (
        client.post(
            "/analyses",
            files={"file": ("sample.csv", HEADER + b"T1,C1,100\n", "text/csv")},
        ).status_code
        == 200
    )
