from dataclasses import asdict

from lucops.agents.money import format_brl_amount
from lucops.agents.presentation import ExecutiveView, build_executive_view
from lucops.agents.service import investigate_transaction

HEADER = "id_transacao,cliente_id,valor\n"


def investigate(tmp_path, rows, index=1):
    path = tmp_path / "synthetic.csv"
    path.write_text(HEADER + rows, encoding="utf-8")
    return asdict(investigate_transaction(path, index, include_ml=False))


def test_executive_view_uses_verified_quality_and_minimized_value(tmp_path):
    result = investigate(tmp_path, "PRIVATE,C1,-20\n")
    view = build_executive_view(result)
    assert view["record_index"] == 1
    assert view["original_value"] == "-20"
    assert "1 inconsistência" in view["quality"]
    assert "Inelegível" in view["ml"]
    assert "pontuação" in view["ml"]
    assert view["mode"] == "simulated"
    assert "pode" in view["hypotheses"][0]["description"]
    assert all(item["evidence_id"] in view["labels"] for item in view["evidence"])
    assert set(view["labels"].values()) == {
        f"E{i}" for i in range(1, len(result["verified_evidence"]) + 1)
    }
    assert all("sha256:" not in label for label in view["labels"].values())
    assert any("não pôde ser avaliado" in item for item in view["limitations"])
    assert "PRIVATE" not in str(view)


def test_first_duplicate_has_verified_peer_even_without_quality_issue(tmp_path):
    result = investigate(tmp_path, "D1,C1,100\nD1,C2,200\n")
    view = build_executive_view(result)
    assert result["context"]["inconsistencies"] == ()
    assert "outro registro com o mesmo identificador" in view["quality"]
    assert any(
        "Identificadores repetidos" in h["description"] for h in view["hypotheses"]
    )
    assert "Indisponível" in view["ml"]
    assert any(item["source"]["field"] == "id_transacao" for item in view["evidence"])


def test_clean_transaction_does_not_gain_invented_risk_status(tmp_path):
    view = build_executive_view(investigate(tmp_path, "T1,C1,100\n"))
    assert "Nenhuma inconsistência" in view["quality"]
    assert view["hypotheses"] == ()
    assert "Indisponível" in view["ml"]
    assert "risco" not in view["summary"].lower()
    assert "fraude" not in view["summary"].lower()


def test_full_ids_scores_and_metadata_remain_in_original_result(tmp_path):
    result = investigate(tmp_path, "T1,C1,100\n")
    view = build_executive_view(result)
    assert result["context"]["dataset_id"].startswith("sha256:")
    assert all(identifier.startswith("sha256:") for identifier in view["labels"])
    assert result["verified_evidence"]
    assert result["context"]["ml"]["status"] == "unavailable"


def test_currency_display_preserves_original_and_private_values(tmp_path):
    result = investigate(tmp_path, "T1,C1,1000000.00\n")
    view = build_executive_view(result)
    assert ExecutiveView.__required_keys__ <= view.keys()
    assert "formatted_value" not in view
    assert format_brl_amount(result["context"]["transaction"]["original_value"]) == (
        "R$ 1.000.000,00"
    )
    assert view["original_value"] == "1000000.00"
    assert result["context"]["transaction"]["original_value"] == "1000000.00"
    assert format_brl_amount("-20") == "-R$ 20,00"
    assert format_brl_amount("0.001") == "0.001"
    assert format_brl_amount("[redacted]") == "Valor ocultado"
    assert format_brl_amount(None) == "Campo ausente"
    assert format_brl_amount("") == "Campo em branco"
    assert format_brl_amount("abc") == "Valor inválido"


def test_executive_summary_is_distinct_from_status_cards(tmp_path):
    invalid = build_executive_view(investigate(tmp_path, "T1,C1,-20\n"))
    assert invalid["summary"] != f"{invalid['quality']} {invalid['ml']}"
    assert "conferência na origem" in invalid["summary"]
    assert "Inelegível" not in invalid["summary"]
    clean = build_executive_view(investigate(tmp_path, "T1,C1,100\n"))
    assert "Não há avaliação estatística" in clean["summary"]


def test_business_evidence_description_matches_visible_amount(tmp_path):
    result = investigate(tmp_path, "T1,C1,100\n")
    view = build_executive_view(result)
    amount = next(
        item
        for item in view["evidence"]
        if item["source"]["function"] == "lucops.ingestion.load_csv"
    )
    assert amount["field_label"] == "Valor"
    assert amount["description"] == "Valor informado no registro do CSV."
    assert result["verified_evidence"][0]["description"] != amount["description"]


def test_redacted_amount_is_not_exposed_in_business_view(tmp_path):
    result = investigate(tmp_path, "T1,C1,secret-text\n")
    view = build_executive_view(result)
    assert format_brl_amount(result["context"]["transaction"]["original_value"]) == (
        "Valor ocultado"
    )
    assert "secret-text" not in str(view)
    assert any(
        item["description"] == "Valor ocultado por proteção de dados."
        for item in view["evidence"]
    )
