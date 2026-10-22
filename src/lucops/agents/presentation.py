"""Read-only executive projection of a server-validated investigation result."""

from typing import TypedDict


class ExecutiveView(TypedDict):
    """Required fields consumed by the Streamlit business presentation."""

    record_index: int
    original_value: str | None
    provider: str
    mode: str
    quality: str
    ml: str
    summary: str
    evidence: list[dict]
    labels: dict[str, str]
    hypotheses: list[dict]
    recommendations: list[dict]
    limitations: tuple[str, ...]


def _business_evidence(item: dict) -> dict:
    """Translate only display text; the verified evidence remains unchanged."""
    field = item["source"]["field"]
    description = {
        "Field is required.": "Campo obrigatório não preenchido.",
        "Rule failed.": "O valor não atende à regra de qualidade.",
        "Duplicate value.": "Identificador repetido neste CSV.",
    }.get(item["description"], item["description"])
    if item["source"]["function"] == "lucops.ingestion.load_csv" and field == "valor":
        description = (
            "Valor ocultado por proteção de dados."
            if item["value"] == "[redacted]"
            else "Valor informado no registro do CSV."
        )
    names = {
        "valor": "Valor",
        "id_transacao": "Identificador da transação",
        "cliente_id": "Identificador do cliente",
        "ml.status": "Situação do ML",
        "is_anomaly": "Alerta estatístico",
        "eligibility": "Elegibilidade para ML",
    }
    return {**item, "field_label": names.get(field, field), "description": description}


def build_executive_view(result: dict) -> ExecutiveView:
    """Select verified facts for display; keep the original result for audit."""
    context = result["context"]
    facts = result["verified_evidence"]
    labels = {item["evidence_id"]: f"E{number}" for number, item in enumerate(facts, 1)}
    issues = context["inconsistencies"]
    ml = context["ml"]
    duplicate = any(
        item["source"]["function"] == "lucops.agents.tools.find_duplicates"
        and item["source"]["field"] == "id_transacao"
        for item in facts
    )
    quality = (
        f"{len(issues)} inconsistência(s) identificada(s) pelas regras de qualidade."
        if issues
        else "Nenhuma inconsistência identificada pelas regras de qualidade."
    )
    if duplicate and not any(issue["field"] == "id_transacao" for issue in issues):
        quality += " Há outro registro com o mesmo identificador neste CSV."
    ml_status = ml["status"]
    if ml_status == "evaluated":
        ml_text = (
            "Avaliado: alerta estatístico identificado."
            if ml["is_anomaly"]
            else "Avaliado: sem alerta estatístico identificado."
        )
    elif ml_status == "ineligible":
        ml_text = "Inelegível: este registro não recebeu pontuação de ML."
    else:
        ml_text = "Indisponível: não há resultado de ML para este registro."
    relevant = [
        item
        for item in facts
        if item["kind"] == "quality"
        and item["source"]["field"] == "id_transacao"
        or item["source"]["function"] == "lucops.pipeline.run_pipeline"
        or item["source"]["field"]
        in {"valor", "ml.status", "is_anomaly", "eligibility"}
    ]
    # Preserve source order and deduplicate while keeping the full audit below.
    main = [
        _business_evidence(item)
        for item in list({item["evidence_id"]: item for item in relevant}.values())[:8]
    ]
    if ml_status == "ineligible":
        essentials = (
            "O registro não pôde ser avaliado pelo ML; consulte os motivos nos detalhes técnicos.",
        )
    elif ml_status == "unavailable":
        essentials = (
            "A ausência de avaliação de ML não equivale à ausência de anomalia.",
        )
    else:
        essentials = ()
    essentials += tuple(result["insufficient_evidence"][:2])
    issue_fields = {item["field"] for item in issues}
    if "valor" in issue_fields:
        summary = (
            "O valor informado exige conferência na origem antes de ser usado "
            "em uma análise estatística."
        )
    elif duplicate:
        summary = (
            "O mesmo identificador aparece em outro registro deste CSV; "
            "os registros precisam ser conferidos na origem."
        )
    elif issues:
        summary = (
            "Há campos que precisam ser conferidos na origem para esclarecer "
            "as inconsistências apontadas pelas regras."
        )
    elif ml_status == "evaluated" and ml["is_anomaly"]:
        summary = (
            "O valor passou pelas regras de qualidade e recebeu um alerta "
            "estatístico. As evidências disponíveis não explicam sua causa."
        )
    elif ml_status == "evaluated":
        summary = (
            "As verificações disponíveis não apontaram inconsistências nem "
            "alerta estatístico para este registro."
        )
    else:
        summary = (
            "As regras de qualidade não apontaram inconsistências neste registro. "
            "Não há avaliação estatística disponível para complementar a análise."
        )
    if issues and duplicate and "id_transacao" not in issue_fields:
        summary += " Há também outro registro com o mesmo identificador neste CSV."
    return {
        "record_index": context["record_index"],
        "original_value": (
            "ocultado"
            if context["transaction"]["original_value"] == "[redacted]"
            else context["transaction"]["original_value"]
        ),
        "provider": result["provider"],
        "mode": result["mode"],
        "quality": quality,
        "ml": ml_text,
        "summary": summary,
        "evidence": main,
        "labels": labels,
        "hypotheses": result["hypotheses"],
        "recommendations": result["recommendations"],
        "limitations": essentials,
    }
