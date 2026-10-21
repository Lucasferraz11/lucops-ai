import builtins
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sklearn.ensemble import IsolationForest
from streamlit.testing.v1 import AppTest

from lucops.api import app
from lucops.ml import service
from lucops.ml.artifacts import load_model, save_model
from lucops.ml.evaluation import make_synthetic_data
from lucops.ml.training import train_detector

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_cache(monkeypatch):
    monkeypatch.delenv("LUCOPS_MODEL_PATH", raising=False)
    service._load_cached_model.cache_clear()
    yield
    service._load_cached_model.cache_clear()


@pytest.fixture
def model_path(tmp_path, monkeypatch):
    training, _, _ = make_synthetic_data()
    path = tmp_path / "trusted.joblib"
    save_model(train_detector(training), path, model_version="api-test")
    monkeypatch.setenv("LUCOPS_MODEL_PATH", str(path))
    return path


def upload(content, **kwargs):
    return client.post(
        "/anomaly-analyses",
        files={"file": ("input.csv", content, "text/csv")},
        **kwargs,
    )


def test_inference_response_and_no_training_or_repeated_loading(model_path):
    content = (
        b"id_transacao,cliente_id,valor\nT1,C1,150.00\nT2,C2,1000000.00\nT3,,-1.00\n"
    )
    with (
        patch.object(IsolationForest, "fit", side_effect=AssertionError("No training")),
        patch("lucops.ml.service.load_model", wraps=load_model) as load,
    ):
        first = upload(content)
        second = upload(content)
    assert first.status_code == 200
    assert first.json() == second.json()
    load.assert_called_once_with(str(model_path.resolve()))
    result = first.json()
    assert result["model_version"] == "api-test"
    assert result["evaluated_records"] == 2
    assert result["skipped_records"] == 1
    assert result["anomalies_detected"] == sum(
        r["is_anomaly"] for r in result["results"]
    )
    assert result["results"][1]["is_anomaly"]
    assert set(result["results"][0]) == {
        "record_index",
        "transaction_id",
        "original_value",
        "anomaly_score",
        "is_anomaly",
    }
    assert result["results"][1]["record_index"] == 2
    assert result["results"][1]["original_value"] == "1000000.00"
    assert result["ineligible"][0]["transaction_id"] == "T3"
    assert {issue["field"] for issue in result["ineligible"][0]["issues"]} == {
        "cliente_id",
        "valor",
    }
    quality = client.post("/analyses", files={"file": ("input.csv", content)})
    assert quality.status_code == 200
    assert quality.json()["summary"]["valid_records"] == 2


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"wrong\nvalue\n",
        b"id_transacao,cliente_id,valor\nT1,C1\n",
        b"id_transacao,cliente_id,valor\nT1,C1,10,extra\n",
        b"id_transacao,cliente_id,valor\nT1,C1,\xff\n",
    ],
)
def test_invalid_csv_returns_400(model_path, content):
    response = upload(content)
    assert response.status_code == 400
    assert "CSV" in response.json()["detail"]


@pytest.mark.parametrize("rows,skipped", [("", 0), ("T1,,-1\n", 1)])
def test_empty_or_ineligible_returns_no_predictions(model_path, rows, skipped):
    response = upload(("id_transacao,cliente_id,valor\n" + rows).encode())
    assert response.status_code == 200
    assert response.json()["results"] == []
    assert response.json()["skipped_records"] == skipped
    assert response.json()["evaluated_records"] == 0


def test_missing_configuration_returns_503_without_affecting_health():
    assert upload(b"anything").status_code == 503
    assert client.get("/health").json() == {"status": "ok", "service": "LucOps AI"}


def test_missing_model_returns_503(tmp_path, monkeypatch):
    monkeypatch.setenv("LUCOPS_MODEL_PATH", str(tmp_path / "missing.joblib"))
    response = upload(b"anything")
    assert response.status_code == 503
    assert str(tmp_path) not in response.json()["detail"]


@pytest.mark.parametrize("problem", ["version", "corrupted", "missing_metadata"])
def test_invalid_artifact_returns_503(model_path, problem):
    sidecar = model_path.with_name(model_path.name + ".json")
    if problem == "version":
        metadata = json.loads(sidecar.read_text())
        metadata["sklearn_version"] = "incompatible"
        sidecar.write_text(json.dumps(metadata))
    elif problem == "corrupted":
        model_path.write_bytes(b"corrupted")
    else:
        sidecar.unlink()
    assert upload(b"anything").status_code == 503


def test_user_cannot_supply_model_path_or_artifact(model_path):
    with patch("lucops.ml.service.load_model", wraps=load_model) as load:
        response = client.post(
            "/anomaly-analyses?model_path=/unknown.joblib",
            data={"model_path": "/unknown.joblib"},
            files={
                "file": (
                    "../../unknown.joblib",
                    b"id_transacao,cliente_id,valor\nT,C,100\n",
                ),
                "model": ("unknown.joblib", b"untrusted data"),
            },
        )
    assert response.status_code == 200
    load.assert_called_once_with(str(model_path.resolve()))


def test_missing_upload_returns_422():
    assert client.post("/anomaly-analyses").status_code == 422


def test_optional_dependencies_unavailable_preserves_health():
    original_import = builtins.__import__

    def without_ml(name, *args, **kwargs):
        if name == "ml.service":
            raise ImportError("ML not installed")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=without_ml):
        assert upload(b"anything").status_code == 503
        assert client.get("/health").status_code == 200


def test_dashboard_upload_through_real_api_and_persisted_model(model_path):
    app_path = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"
    content = b"id_transacao,cliente_id,valor\nT1,C1,150.00\nT2,C2,1000000.00\n"
    with (
        patch("requests.get") as get,
        patch("requests.post") as post,
        patch.object(IsolationForest, "fit", side_effect=AssertionError("No training")),
    ):
        get.return_value.json.return_value = {"status": "ok"}

        def forward_to_api(url, **kwargs):
            return client.post(
                "/" + url.rsplit("/", 1)[-1],
                files=kwargs["files"],
            )

        post.side_effect = forward_to_api
        dashboard = AppTest.from_file(str(app_path)).run(timeout=20)
        dashboard.file_uploader[0].upload(
            "new.csv",
            content,
            "text/csv",
        ).run(timeout=20)
        dashboard.button[0].click().run(timeout=20)
        quality_before = dashboard.session_state["analysis_result"]
        dashboard.button(key="analyze_anomalies").click().run(timeout=20)
    assert not dashboard.exception
    assert dashboard.session_state["analysis_result"] == quality_before
    assert quality_before["summary"]["valid_records"] == 2
    assert dashboard.session_state["anomaly_result"]["model_version"] == "api-test"
    assert "T2" in dashboard.dataframe[0].value["ID da transação"].tolist()
