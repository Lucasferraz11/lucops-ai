import csv
import hashlib
import io
import os

import requests
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from lucops.agents.money import format_brl_amount
from lucops.agents.presentation import build_executive_view


def get_api_base_url() -> str:
    api_base_url = os.getenv("LUCOPS_API_URL")

    if api_base_url is None:
        try:
            api_base_url = st.secrets["LUCOPS_API_URL"]
        except (KeyError, StreamlitSecretNotFoundError):
            api_base_url = "http://127.0.0.1:8000"

    if not isinstance(api_base_url, str) or not api_base_url.strip():
        raise ValueError("LUCOPS_API_URL deve conter a URL base da API.")

    return api_base_url.strip().rstrip("/")


API_BASE_URL = get_api_base_url()
QUALITY_CARD_HEIGHT = 160

st.set_page_config(
    page_title="LucOps AI | Dashboard",
    page_icon="📊",
    layout="wide",
)

# Armazena o resultado da última análise
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

if "anomaly_result" not in st.session_state:
    st.session_state.anomaly_result = None

if "investigation_result" not in st.session_state:
    st.session_state.investigation_result = None

if "investigation_selection" not in st.session_state:
    st.session_state.investigation_selection = None

if "uploaded_file_id" not in st.session_state:
    st.session_state.uploaded_file_id = None


# Menu lateral
with st.sidebar:
    st.title("LucOps AI")
    st.caption("Data Quality & Reliability")
    st.divider()

    st.subheader("Módulos")
    st.write("✅ Qualidade de Dados")
    st.write("✅ API de Análises")
    st.write("🚧 Analytics e Dashboards")
    st.write("✅ Machine Learning")
    st.write("🔜 Agentes de IA")

    st.divider()
    st.subheader("Status da API")

    try:
        response = requests.get(
            f"{API_BASE_URL}/health",
            timeout=5,
        )
        response.raise_for_status()

        if response.json().get("status") == "ok":
            st.success("API conectada")
        else:
            st.warning("Resposta inesperada da API.")

    except requests.RequestException:
        st.error("API indisponível")


# Conteúdo principal
st.title("Dashboard de Qualidade de Dados")
st.caption("Intelligent Data Quality & Reliability Platform")
st.divider()

st.write(
    "Monitore a qualidade dos seus dados, identifique "
    "inconsistências e acompanhe os resultados das análises."
)

# Organização do dashboard
col_analysis = st.container()
col_results = st.container()


# Coluna 1 - Nova análise
with col_analysis, st.container(border=True):
    st.subheader("Nova análise")

    st.write("Envie um arquivo CSV para executar uma análise de qualidade de dados.")

    uploaded_file = st.file_uploader(
        "Selecione um arquivo CSV",
        type=["csv"],
        accept_multiple_files=False,
    )

    # Identifica mudanças no arquivo selecionado
    current_file_id = None

    if uploaded_file is not None:
        file_hash = hashlib.sha256(uploaded_file.getvalue()).hexdigest()
        current_file_id = (uploaded_file.name, file_hash)

    if current_file_id != st.session_state.uploaded_file_id:
        st.session_state.analysis_result = None
        st.session_state.anomaly_result = None
        st.session_state.investigation_result = None
        st.session_state.investigation_selection = None
        st.session_state.uploaded_file_id = current_file_id

    if uploaded_file is not None:
        st.success("Arquivo selecionado com sucesso!")
        st.write(f"Nome do arquivo: {uploaded_file.name}")
        st.caption("Arquivo pronto para análise.")

        if st.button("Analisar dados", type="primary"):
            # Limpa os resultados anteriores
            st.session_state.analysis_result = None

            try:
                with st.spinner("Analisando os dados..."):
                    response = requests.post(
                        f"{API_BASE_URL}/analyses",
                        files={
                            "file": (
                                uploaded_file.name,
                                uploaded_file.getvalue(),
                                "text/csv",
                            )
                        },
                        timeout=30,
                    )

                if response.status_code == 200:
                    st.session_state.analysis_result = response.json()
                    st.success("Análise concluída com sucesso!")

                else:
                    st.error(f"Erro na análise: HTTP {response.status_code}")
                    st.write(response.text)

            except requests.RequestException as exc:
                st.error(f"Não foi possível acessar a API: {exc}")


# Coluna 2 - Resultados
with col_results, st.container(border=True):
    st.subheader("Resultados")

    if st.session_state.analysis_result is None:
        st.info("Nenhuma análise executada.")

    else:
        result = st.session_state.analysis_result
        summary = result["summary"]
        status = result["quality_status"]

        # Mensagens de status
        if status == "COM INCONSISTÊNCIAS":
            st.warning("⚠️ Foram identificadas inconsistências nos dados.")

        elif status == "SEM INCONSISTÊNCIAS":
            st.success("✅ Nenhuma inconsistência identificada.")

        elif status == "SEM DADOS":
            st.info("ℹ️ Não há registros para analisar.")

        else:
            st.info(f"Status da análise: {status}")

        st.divider()

        # Indicadores à esquerda e gráfico à direita
        col_metrics, col_chart = st.columns(
            [3, 2], gap="medium", vertical_alignment="top"
        )

        # Coluna esquerda - Indicadores
        with col_metrics:
            st.subheader("Indicadores de qualidade")

            # Primeira linha de indicadores
            col_total, col_valid = st.columns(2, gap="small")

            with col_total, st.container(border=True, height=QUALITY_CARD_HEIGHT):
                st.metric(
                    "Total de registros",
                    summary["total_records"],
                )
                st.html(
                    '<div style="width:32px;height:4px;'
                    'background:#397DFA;border-radius:999px;"></div>'
                )

            with col_valid, st.container(border=True, height=QUALITY_CARD_HEIGHT):
                st.metric(
                    "Registros válidos",
                    summary["valid_records"],
                )
                st.html(
                    '<div style="width:32px;height:4px;'
                    'background:#22C55E;border-radius:999px;"></div>'
                )

            # Segunda linha de indicadores
            col_invalid, col_percentage = st.columns(2, gap="small")

            with col_invalid, st.container(border=True, height=QUALITY_CARD_HEIGHT):
                st.metric(
                    "Registros inválidos",
                    summary["invalid_records"],
                )
                st.html(
                    '<div style="width:32px;height:4px;'
                    'background:#EF4444;border-radius:999px;"></div>'
                )

            with col_percentage:
                percentage = summary["valid_percentage"]

                formatted_percentage = (
                    f"{percentage:.2f}%" if percentage is not None else "N/D"
                )

                if percentage is None:
                    accent_color = "#64748B"
                elif percentage == 100:
                    accent_color = "#22C55E"
                elif percentage >= 50:
                    accent_color = "#F59E0B"
                else:
                    accent_color = "#EF4444"

                with st.container(border=True, height=QUALITY_CARD_HEIGHT):
                    st.metric(
                        "Taxa de validade",
                        formatted_percentage,
                    )
                    st.html(
                        f'<div style="width:32px;height:4px;'
                        f"background:{accent_color};"
                        f'border-radius:999px;"></div>'
                    )

            # Barra de qualidade com cores dinâmicas
            st.divider()
            st.subheader("Índice de qualidade dos dados")

            quality_percentage = summary["valid_percentage"]

            if quality_percentage is not None:
                if quality_percentage == 100:
                    bar_color = "#22C55E"

                elif quality_percentage >= 50:
                    bar_color = "#F59E0B"

                else:
                    bar_color = "#EF4444"

                st.write(f"Taxa de validade: {quality_percentage:.2f}%")

                st.html(
                    f"""
                    <div
                        role="progressbar"
                        aria-label="Taxa de validade"
                        aria-valuenow="{quality_percentage:.2f}"
                        aria-valuemin="0"
                        aria-valuemax="100"
                        style="
                            width: 100%;
                            height: 12px;
                            background-color: #17243A;
                            border-radius: 999px;
                            overflow: hidden;
                        "
                    >
                        <div
                            style="
                                width: {quality_percentage:.2f}%;
                                height: 100%;
                                background-color: {bar_color};
                                border-radius: 999px;
                            "
                        ></div>
                    </div>
                    """
                )

            else:
                st.info("Não há dados suficientes para calcular a qualidade.")

        # Coluna direita - Gráfico
        with col_chart:
            st.subheader("Distribuição dos registros")

            with st.container(border=True):
                if summary["total_records"] > 0:
                    chart_data = [
                        {
                            "categoria": "Válidos",
                            "quantidade": summary["valid_records"],
                        },
                        {
                            "categoria": "Inválidos",
                            "quantidade": summary["invalid_records"],
                        },
                    ]

                    percentage_value = summary["valid_percentage"] or 0
                    percentage_label = f"{percentage_value:.0f}%"

                    # Gráfico de rosca
                    st.vega_lite_chart(
                        chart_data,
                        {
                            "width": "container",
                            "height": 260,
                            "layer": [
                                {
                                    "mark": {
                                        "type": "arc",
                                        "innerRadius": 62,
                                        "outerRadius": 100,
                                    },
                                    "encoding": {
                                        "theta": {
                                            "field": "quantidade",
                                            "type": "quantitative",
                                        },
                                        "color": {
                                            "field": "categoria",
                                            "type": "nominal",
                                            "scale": {
                                                "domain": [
                                                    "Válidos",
                                                    "Inválidos",
                                                ],
                                                "range": [
                                                    "#22C55E",
                                                    "#EF4444",
                                                ],
                                            },
                                            "legend": None,
                                        },
                                        "tooltip": [
                                            {
                                                "field": "categoria",
                                                "type": "nominal",
                                            },
                                            {
                                                "field": "quantidade",
                                                "type": "quantitative",
                                            },
                                        ],
                                    },
                                },
                                # Percentual centralizado
                                {
                                    "data": {"values": [{"label": percentage_label}]},
                                    "mark": {
                                        "type": "text",
                                        "radius": 0,
                                        "dy": -12,
                                        "fontSize": 28,
                                        "fontWeight": "bold",
                                        "color": "#F3F6FD",
                                        "align": "center",
                                        "baseline": "middle",
                                    },
                                    "encoding": {
                                        "text": {
                                            "field": "label",
                                        },
                                    },
                                },
                                # Subtítulo centralizado
                                {
                                    "data": {"values": [{"label": "Taxa de validade"}]},
                                    "mark": {
                                        "type": "text",
                                        "radius": 0,
                                        "dy": 16,
                                        "fontSize": 11,
                                        "color": "#AAB6CF",
                                        "align": "center",
                                        "baseline": "middle",
                                    },
                                    "encoding": {
                                        "text": {
                                            "field": "label",
                                        },
                                    },
                                },
                            ],
                            "view": {
                                "stroke": None,
                            },
                        },
                        use_container_width=True,
                    )

                    # Legenda abaixo do gráfico
                    st.html(
                        """
                        <div
                            style="
                                display: flex;
                                justify-content: center;
                                align-items: center;
                                gap: 24px;
                                flex-wrap: wrap;
                                padding: 4px 0 12px;
                            "
                        >
                            <span
                                style="
                                    display: flex;
                                    align-items: center;
                                    gap: 7px;
                                "
                            >
                                <span
                                    style="
                                        width: 12px;
                                        height: 12px;
                                        border-radius: 50%;
                                        background-color: #22C55E;
                                    "
                                ></span>
                                Válidos
                            </span>

                            <span
                                style="
                                    display: flex;
                                    align-items: center;
                                    gap: 7px;
                                "
                            >
                                <span
                                    style="
                                        width: 12px;
                                        height: 12px;
                                        border-radius: 50%;
                                        background-color: #EF4444;
                                    "
                                ></span>
                                Inválidos
                            </span>
                        </div>
                        """
                    )

                else:
                    st.info("Não há registros para gerar o gráfico.")

# ML has independent results and never changes the traditional quality status.
with st.container(border=True):
    st.subheader("Machine Learning | Alertas estatísticos")
    st.info(
        "O Isolation Forest identifica valores atípicos em relação ao histórico "
        "de treinamento. Alertas estatísticos não confirmam fraude e não alteram "
        "o status de qualidade dos dados."
    )
    st.caption(
        "Apenas o valor da transação é analisado. A pontuação não é uma "
        "probabilidade; valores positivos geram alerta. O modelo ainda requer "
        "validação com dados reais e pode produzir falsos positivos."
    )

    if uploaded_file is None:
        st.write("Selecione um CSV na seção Nova análise para analisar anomalias.")
    elif st.button("Detectar anomalias", key="analyze_anomalies"):
        st.session_state.anomaly_result = None
        try:
            with st.spinner("Analisando anomalias..."):
                response = requests.post(
                    f"{API_BASE_URL}/anomaly-analyses",
                    files={
                        "file": (
                            uploaded_file.name,
                            uploaded_file.getvalue(),
                            "text/csv",
                        )
                    },
                    timeout=30,
                )
            if response.status_code == 200:
                st.session_state.anomaly_result = response.json()
            elif response.status_code == 503:
                st.error(
                    "Análise de ML indisponível. O administrador deve configurar "
                    "um modelo treinado compatível no servidor."
                )
            elif response.status_code == 400:
                st.error("CSV inválido para análise de anomalias.")
            else:
                st.error(f"Erro na análise de ML: HTTP {response.status_code}")
        except (requests.RequestException, ValueError):
            st.error("Não foi possível obter a análise de ML. Tente novamente.")

    if st.session_state.anomaly_result is not None:
        ml_result = st.session_state.anomaly_result
        st.caption(f"Modelo: {ml_result['model_version']}")
        evaluated, skipped, flagged = st.columns(3)
        evaluated.metric("Transações avaliadas (ML)", ml_result["evaluated_records"])
        skipped.metric("Transações ignoradas (ML)", ml_result["skipped_records"])
        flagged.metric("Transações sinalizadas (ML)", ml_result["anomalies_detected"])
        anomalies = [record for record in ml_result["results"] if record["is_anomaly"]]
        if anomalies:
            st.warning("Alertas estatísticos para investigação")
            st.dataframe(
                [
                    {
                        "Índice": record["record_index"],
                        "ID da transação": record["transaction_id"],
                        "Valor original": record["original_value"],
                        "Pontuação": record["anomaly_score"],
                    }
                    for record in anomalies
                ],
                hide_index=True,
            )
        elif ml_result["evaluated_records"]:
            st.info("Nenhuma transação sinalizada pelo modelo.")
        else:
            st.info("Nenhuma transação elegível para análise de ML.")

        if ml_result["ineligible"]:
            with st.expander("Registros ignorados e motivos de qualidade"):
                st.dataframe(
                    [
                        {
                            "Índice": record["record_index"],
                            "ID da transação": record["transaction_id"],
                            "Valor original": record["original_value"],
                            "Motivos": "; ".join(
                                f"{issue['field']}: {issue['message']}"
                                for issue in record["issues"]
                            ),
                        }
                        for record in ml_result["ineligible"]
                    ],
                    hide_index=True,
                )


with st.container(border=True):
    st.subheader("Investigação com IA")
    st.caption(
        "Evidências verificadas vêm do servidor. Hipóteses são possibilidades "
        "não confirmadas; alertas de ML não são prova de fraude."
    )
    if uploaded_file is None:
        st.info("Selecione um CSV para investigar uma transação.")
    else:
        try:
            content = uploaded_file.getvalue().decode("utf-8-sig")
            record_count = sum(1 for _ in csv.DictReader(io.StringIO(content)))
        except (UnicodeError, csv.Error):
            record_count = 0
            st.error("Não foi possível listar os registros do CSV.")
        if record_count == 0:
            st.info("Nenhuma transação disponível para investigação.")
        else:
            selected_index = st.selectbox(
                "Transação do CSV",
                range(1, record_count + 1),
                format_func=lambda index: f"Registro {index}",
                key="investigation_record_index",
            )
            selected_provider = st.selectbox(
                "Provedor",
                ("simulated", "openai"),
                key="investigation_provider",
            )
            selection = (current_file_id, selected_index, selected_provider)
            if selection != st.session_state.investigation_selection:
                st.session_state.investigation_result = None
                st.session_state.investigation_selection = selection
            if selected_provider == "openai":
                st.caption(
                    "O modo OpenAI requer configuração e liberação de chamadas "
                    "no backend. A chave nunca é enviada pelo dashboard."
                )
            if st.button("Investigar com IA", key="investigate_transaction"):
                st.session_state.investigation_result = None
                try:
                    with st.spinner("Investigando a transação..."):
                        response = requests.post(
                            f"{API_BASE_URL}/investigations",
                            files={
                                "file": (
                                    uploaded_file.name,
                                    uploaded_file.getvalue(),
                                    "text/csv",
                                )
                            },
                            data={
                                "record_index": selected_index,
                                "provider": selected_provider,
                            },
                            timeout=35,
                        )
                    if response.status_code == 200:
                        st.session_state.investigation_result = response.json()
                    elif response.status_code == 404:
                        st.error("A transação selecionada não foi encontrada no CSV.")
                    elif response.status_code == 400:
                        st.error("CSV inválido para investigação.")
                    elif response.status_code in (422, 503):
                        st.error(
                            "Investigação indisponível ou configuração inválida. "
                            "Verifique o provedor no servidor."
                        )
                    else:
                        st.error(f"Falha na investigação: HTTP {response.status_code}")
                except (requests.RequestException, ValueError):
                    st.error(
                        "Não foi possível concluir a investigação. Tente novamente."
                    )

            investigation = st.session_state.investigation_result
            if investigation is not None:
                view = build_executive_view(investigation)
                if view["mode"] == "simulated":
                    st.info(
                        "Provedor: simulated — resposta determinística; nenhum LLM foi chamado."
                    )
                else:
                    st.info(f"Provedor: {view['provider']} — modo openai")
                st.markdown("**Visão de negócio**")
                ml = investigation["context"]["ml"]
                quality_label = (
                    "Com inconsistências"
                    if investigation["context"]["inconsistencies"]
                    else "Sem inconsistências"
                )
                if (
                    not investigation["context"]["inconsistencies"]
                    and "outro registro com o mesmo identificador" in view["quality"]
                ):
                    quality_label = "ID repetido no CSV"
                ml_label = {
                    "evaluated": (
                        "Alerta estatístico" if ml["is_anomaly"] else "Sem alerta"
                    ),
                    "ineligible": "Inelegível",
                    "unavailable": "Indisponível",
                }[ml["status"]]
                for column, title, value in zip(
                    st.columns(4, gap="small"),
                    ("Registro", "Valor", "Qualidade", "Machine Learning"),
                    (
                        str(view["record_index"]),
                        format_brl_amount(
                            investigation["context"]["transaction"]["original_value"]
                        ),
                        quality_label,
                        ml_label,
                    ),
                    strict=True,
                ):
                    with column, st.container(border=True):
                        st.metric(title, value)
                st.write(view["summary"])
                st.markdown("**Evidências principais**")
                st.dataframe(
                    [
                        {
                            "Ref.": view["labels"][item["evidence_id"]],
                            "Campo": item["field_label"],
                            "Valor": (
                                "Ocultado"
                                if item["value"] == "[redacted]"
                                else item["value"]
                            ),
                            "Descrição": item["description"],
                        }
                        for item in view["evidence"]
                    ],
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Ref.": st.column_config.TextColumn(width="small"),
                        "Campo": st.column_config.TextColumn(width="medium"),
                        "Descrição": st.column_config.TextColumn(width="large"),
                    },
                )
                st.markdown("**Hipóteses não confirmadas**")
                if view["hypotheses"]:
                    for item in view["hypotheses"]:
                        st.warning(item["description"])
                        st.caption(
                            "Evidências: "
                            + ", ".join(
                                view["labels"][ref] for ref in item["evidence_ids"]
                            )
                        )
                else:
                    st.info("Nenhuma hipótese fundamentada foi produzida.")
                st.markdown("**Recomendações**")
                for item in view["recommendations"]:
                    st.write(item["action"])
                    st.caption(
                        "Evidências: "
                        + ", ".join(view["labels"][ref] for ref in item["evidence_ids"])
                    )
                if view["limitations"]:
                    st.markdown("**Limitações essenciais**")
                    for item in view["limitations"]:
                        st.write(item)
                with st.expander("Ver detalhes técnicos"):
                    st.caption(
                        "As referências completas, pontuações, origens e metadados "
                        "permanecem disponíveis para auditoria."
                    )
                    st.dataframe(
                        [
                            {
                                "Ref.": view["labels"][item["evidence_id"]],
                                "ID completo": item["evidence_id"],
                                "Origem": item["source"]["function"],
                                "Campo": item["source"]["field"],
                                "Valor": item["value"],
                                "Descrição": item["description"],
                            }
                            for item in investigation["verified_evidence"]
                        ],
                        hide_index=True,
                        width="stretch",
                        column_config={
                            "ID completo": st.column_config.TextColumn(width="large"),
                            "Origem": st.column_config.TextColumn(width="large"),
                            "Descrição": st.column_config.TextColumn(width="large"),
                        },
                    )
                    evidence_options = investigation["verified_evidence"]
                    if evidence_options:
                        selected_evidence = st.selectbox(
                            "Consultar referência completa",
                            range(len(evidence_options)),
                            format_func=lambda index: (
                                f"{view['labels'][evidence_options[index]['evidence_id']]} "
                                f"— {evidence_options[index]['source']['field']}"
                            ),
                            key="investigation_technical_reference",
                        )
                        st.code(
                            evidence_options[selected_evidence]["evidence_id"],
                            language=None,
                        )
                    st.json(investigation, expanded=False)
