from fastapi.testclient import TestClient

from lucops.api import app

client = TestClient(app)


def test_health_check_returns_200():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "LucOps AI",
    }


def test_create_analysis_returns_quality_summary():
    csv_content = (
        b"id_transacao,cliente_id,valor\n"
        b"T001,C001,150.00\n"
        b"T002,C002,-20.00\n"
        b"T001,C003,350.00\n"
    )

    response = client.post(
        "/analyses",
        files={
            "file": (
                "transacoes.csv",
                csv_content,
                "text/csv",
            )
        },
    )

    assert response.status_code == 200

    assert response.json() == {
        "quality_status": "COM INCONSISTÊNCIAS",
        "summary": {
            "total_records": 3,
            "valid_records": 1,
            "invalid_records": 2,
            "total_issues": 2,
            "valid_percentage": 33.33,
        },
    }


def test_create_analysis_rejects_missing_columns():
    csv_content = b"id_transacao,valor\nT001,150.00\n"

    response = client.post(
        "/analyses",
        files={
            "file": (
                "transacoes.csv",
                csv_content,
                "text/csv",
            )
        },
    )

    assert response.status_code == 400

    assert response.json() == {
        "detail": ("CSV inválido: Missing required CSV columns: cliente_id")
    }
