from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"
CSV_ONE = b"id_transacao,cliente_id,valor\nA,C1,100\nA,C2,-20\n"
CSV_TWO = b"id_transacao,cliente_id,valor\nB,C3,200\n"


def response_for(index):
    return {
        "mode": "simulated",
        "provider": "deterministic-rules-v1",
        "context": {
            "record_index": index,
            "transaction": {
                "reference": f"dataset:record:{index}",
                "original_value": "-20",
            },
            "inconsistencies": [{"field": "valor"}],
            "ml": {
                "status": "ineligible",
                "is_anomaly": None,
                "reasons": ["valor inválido"],
            },
        },
        "verified_evidence": [
            {
                "evidence_id": "e1",
                "kind": "quality",
                "source": {
                    "function": "lucops.pipeline.run_pipeline",
                    "field": "valor",
                },
                "value": "-20",
                "description": "Rule failed.",
            }
        ],
        "hypotheses": [
            {"description": "The amount may be invalid.", "evidence_ids": ["e1"]}
        ],
        "recommendations": [
            {"action": "Review the source amount.", "evidence_ids": ["e1"]}
        ],
        "limitations": ["Current CSV only."],
        "insufficient_evidence": ["Cause not confirmed."],
    }


def button(app, label):
    return next(item for item in app.button if item.label == label)


def select(app, label):
    return next(item for item in app.selectbox if item.label == label)


def test_investigation_request_and_selection_reset():
    with patch("requests.get") as health, patch("requests.post") as post:
        health.return_value.json.return_value = {"status": "ok"}
        post.return_value.status_code = 200
        post.return_value.json.return_value = response_for(1)
        app = AppTest.from_file(str(APP)).run(timeout=10)
        app.file_uploader[0].upload("one.csv", CSV_ONE, "text/csv").run(timeout=10)
        button(app, "Investigar com IA").click().run(timeout=10)
        assert not app.exception
        assert app.session_state["investigation_result"]["context"]["record_index"] == 1
        assert post.call_args.kwargs["data"] == {
            "record_index": 1,
            "provider": "simulated",
        }
        assert post.call_args.kwargs["files"]["file"][1] == CSV_ONE
        assert any("Provedor: simulated" in item.value for item in app.main.info)
        assert any(
            expander.label == "Ver detalhes técnicos" for expander in app.expander
        )
        assert len(app.main.dataframe) >= 2
        assert any("Visão de negócio" in item.value for item in app.main.markdown)
        assert {item.label for item in app.main.metric} >= {
            "Registro",
            "Valor",
            "Qualidade",
            "Machine Learning",
        }
        assert any(item.value == "-R$ 20,00" for item in app.main.metric)
        assert select(app, "Consultar referência completa").value == 0
        assert any("e1" in item.value for item in app.main.code)
        select(app, "Transação do CSV").set_value(2).run(timeout=10)
        assert app.session_state["investigation_result"] is None
        post.return_value.json.return_value = response_for(2)
        button(app, "Investigar com IA").click().run(timeout=10)
        assert app.session_state["investigation_result"]["context"]["record_index"] == 2
        select(app, "Provedor").set_value("openai").run(timeout=10)
        assert app.session_state["investigation_result"] is None
        app.file_uploader[0].upload("two.csv", CSV_TWO, "text/csv").run(timeout=10)
        assert app.session_state["investigation_result"] is None
        assert app.session_state["analysis_result"] is None
        assert app.session_state["anomaly_result"] is None


def test_investigation_api_error_is_clear_and_does_not_keep_old_result():
    with patch("requests.get") as health, patch("requests.post") as post:
        health.return_value.json.return_value = {"status": "ok"}
        post.return_value.status_code = 503
        app = AppTest.from_file(str(APP)).run(timeout=10)
        app.file_uploader[0].upload("one.csv", CSV_ONE, "text/csv").run(timeout=10)
        button(app, "Investigar com IA").click().run(timeout=10)
        assert not app.exception
        assert app.session_state["investigation_result"] is None
        assert any("Investigação indisponível" in item.value for item in app.main.error)


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("1000000.00", "R$ 1.000.000,00"),
        ("", "Campo em branco"),
        (None, "Campo ausente"),
        ("[redacted]", "Valor ocultado"),
        ("abc", "Valor inválido"),
    ],
)
def test_dashboard_formats_value_from_server_result(raw_value, expected):
    response = response_for(1)
    response["context"]["transaction"]["original_value"] = raw_value
    with patch("requests.get") as health, patch("requests.post") as post:
        health.return_value.json.return_value = {"status": "ok"}
        post.return_value.status_code = 200
        post.return_value.json.return_value = response
        app = AppTest.from_file(str(APP)).run(timeout=10)
        app.file_uploader[0].upload("one.csv", CSV_ONE, "text/csv").run(timeout=10)
        button(app, "Investigar com IA").click().run(timeout=10)
        assert not app.exception
        assert next(
            item.value for item in app.main.metric if item.label == "Valor"
        ) == (expected)
        assert app.session_state["investigation_result"] is response
        assert any(
            expander.label == "Ver detalhes técnicos" for expander in app.expander
        )
