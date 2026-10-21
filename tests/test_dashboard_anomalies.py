from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
from requests.exceptions import ConnectionError
from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"
CSV = b"id_transacao,cliente_id,valor\nT1,C1,100.00\n"
RESULT = {
    "model_version": "ui-test",
    "evaluated_records": 2,
    "skipped_records": 1,
    "anomalies_detected": 1,
    "results": [
        {
            "record_index": 1,
            "transaction_id": "typical",
            "original_value": "100.00",
            "anomaly_score": -0.1,
            "is_anomaly": False,
        },
        {
            "record_index": 2,
            "transaction_id": "extreme",
            "original_value": "10000.00",
            "anomaly_score": 0.2,
            "is_anomaly": True,
        },
    ],
    "ineligible": [
        {
            "record_index": 3,
            "transaction_id": "bad",
            "original_value": "-1",
            "issues": [{"field": "valor", "message": "Rule failed."}],
        },
    ],
}


def uploaded_app():
    app = AppTest.from_file(str(APP_PATH)).run(timeout=20)
    app.file_uploader[0].upload("input.csv", CSV, "text/csv").run(timeout=20)
    return app


def click_ml(app):
    return app.button(key="analyze_anomalies").click().run(timeout=20)


def test_ml_upload_metrics_table_and_quality_independence():
    with patch("requests.get") as get, patch("requests.post") as post:
        get.return_value.json.return_value = {"status": "ok"}
        post.return_value.status_code = 200
        post.return_value.json.return_value = deepcopy(RESULT)
        app = uploaded_app()
        click_ml(app)
    assert not app.exception
    assert app.session_state["analysis_result"] is None
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Transações avaliadas (ML)"] == "2"
    assert metrics["Transações ignoradas (ML)"] == "1"
    assert metrics["Transações sinalizadas (ML)"] == "1"
    assert app.dataframe[0].value["ID da transação"].tolist() == ["extreme"]
    assert app.dataframe[0].value["Valor original"].tolist() == ["10000.00"]
    assert app.dataframe[0].value["Pontuação"].tolist() == [0.2]
    assert "valor: Rule failed." in app.dataframe[1].value["Motivos"][0]
    assert any("não confirmam fraude" in message.value for message in app.info)
    assert post.call_args.args[0].endswith("/anomaly-analyses")
    assert post.call_args.kwargs["files"]["file"][1] == CSV


@pytest.mark.parametrize("status", [400, 503, 500])
def test_ml_http_failure_clears_old_result(status):
    with patch("requests.get") as get, patch("requests.post") as post:
        get.return_value.json.return_value = {"status": "ok"}
        post.return_value.status_code = status
        app = uploaded_app()
        app.session_state["anomaly_result"] = deepcopy(RESULT)
        click_ml(app)
    assert not app.exception
    assert app.session_state["anomaly_result"] is None
    assert app.error


def test_ml_network_failure_keeps_quality_result():
    with patch("requests.get") as get, patch("requests.post") as post:
        get.return_value.json.return_value = {"status": "ok"}
        post.side_effect = ConnectionError("offline")
        app = uploaded_app()
        quality = {
            "quality_status": "SEM DADOS",
            "summary": {
                "total_records": 0,
                "valid_records": 0,
                "invalid_records": 0,
                "total_issues": 0,
                "valid_percentage": None,
            },
        }
        app.session_state["analysis_result"] = quality
        click_ml(app)
    assert not app.exception
    assert app.session_state["analysis_result"] == quality
    assert app.error


def test_changing_file_clears_ml_result_even_with_same_filename():
    with patch("requests.get") as get, patch("requests.post") as post:
        get.return_value.json.return_value = {"status": "ok"}
        post.return_value.status_code = 200
        post.return_value.json.return_value = deepcopy(RESULT)
        app = uploaded_app()
        click_ml(app)
        app.file_uploader[0].upload(
            "input.csv",
            CSV.replace(b"100.00", b"200.00"),
            "text/csv",
        ).run(timeout=20)
    assert not app.exception
    assert app.session_state["anomaly_result"] is None
    assert not app.dataframe


@pytest.mark.parametrize("evaluated", [0, 2])
def test_ml_no_anomalies_and_no_eligible_records(evaluated):
    with patch("requests.get") as get:
        get.return_value.json.return_value = {"status": "ok"}
        app = AppTest.from_file(str(APP_PATH))
        app.session_state["anomaly_result"] = {
            "model_version": "empty",
            "evaluated_records": evaluated,
            "skipped_records": 0,
            "anomalies_detected": 0,
            "results": [],
            "ineligible": [],
        }
        app.run(timeout=20)
    assert not app.exception
    assert not app.dataframe
    assert any(
        ("Nenhuma transação sinalizada" if evaluated else "Nenhuma transação elegível")
        in message.value
        for message in app.info
    )
