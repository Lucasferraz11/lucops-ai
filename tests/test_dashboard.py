from pathlib import Path
from unittest.mock import patch

from requests.exceptions import ConnectionError as RequestsConnectionError
from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"


def test_dashboard_initial_state():
    # Simula uma resposta positiva da API
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"status": "ok"}

        # Executa o dashboard sem abrir o navegador
        app = AppTest.from_file(str(APP_PATH)).run(timeout=10)

    # Verifica se o dashboard iniciou sem erros
    assert not app.exception

    # Verifica o título principal
    assert app.main.title[0].value == "Dashboard de Qualidade de Dados"

    # Verifica o status da API
    assert any(message.value == "API conectada" for message in app.sidebar.success)

    # Verifica a mensagem exibida antes de qualquer análise
    assert any(
        message.value == "Nenhuma análise executada." for message in app.main.info
    )


def test_dashboard_api_unavailable():
    # Simula uma falha de conexão com a API
    with patch(
        "requests.get",
        side_effect=RequestsConnectionError("Conexão recusada"),
    ):
        app = AppTest.from_file(str(APP_PATH)).run(timeout=10)

    # O dashboard não deve apresentar uma exceção
    assert not app.exception

    # A interface deve informar que a API está indisponível
    assert any(message.value == "API indisponível" for message in app.sidebar.error)

    # A área de resultados deve continuar funcionando
    assert any(
        message.value == "Nenhuma análise executada." for message in app.main.info
    )


def test_dashboard_displays_invalid_records():
    # Simula o resultado de uma análise de qualidade
    analysis_result = {
        "quality_status": "COM INCONSISTÊNCIAS",
        "summary": {
            "total_records": 4,
            "valid_records": 1,
            "invalid_records": 3,
            "total_issues": 3,
            "valid_percentage": 25.0,
        },
    }

    # Simula a API conectada
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"status": "ok"}

        # Inicializa o dashboard
        app = AppTest.from_file(str(APP_PATH))

        # Insere o resultado simulado na sessão
        app.session_state["analysis_result"] = analysis_result

        # Executa o dashboard
        app.run(timeout=10)

    # Verifica se não ocorreram erros
    assert not app.exception

    # Recupera os indicadores apresentados
    metrics = {metric.label: str(metric.value) for metric in app.main.metric}

    # Confere os valores exibidos
    assert metrics["Total de registros"] == "4"
    assert metrics["Registros válidos"] == "1"
    assert metrics["Registros inválidos"] == "3"
    assert metrics["Taxa de validade"] == "25.00%"

    # Confere a mensagem de inconsistências
    assert any(
        "Foram identificadas inconsistências" in message.value
        for message in app.main.warning
    )


def test_dashboard_displays_valid_records():
    # Simula uma análise com 100% de qualidade
    analysis_result = {
        "quality_status": "SEM INCONSISTÊNCIAS",
        "summary": {
            "total_records": 3,
            "valid_records": 3,
            "invalid_records": 0,
            "total_issues": 0,
            "valid_percentage": 100.0,
        },
    }

    # Simula a API conectada
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"status": "ok"}

        # Inicializa o dashboard
        app = AppTest.from_file(str(APP_PATH))

        # Insere os resultados simulados na sessão
        app.session_state["analysis_result"] = analysis_result

        # Executa a aplicação
        app.run(timeout=10)

    # Verifica se o dashboard executou sem erros
    assert not app.exception

    # Recupera os indicadores exibidos
    metrics = {metric.label: str(metric.value) for metric in app.main.metric}

    # Confere os valores dos indicadores
    assert metrics["Total de registros"] == "3"
    assert metrics["Registros válidos"] == "3"
    assert metrics["Registros inválidos"] == "0"
    assert metrics["Taxa de validade"] == "100.00%"

    # Confere a mensagem de sucesso
    assert any(
        "Nenhuma inconsistência identificada" in message.value
        for message in app.main.success
    )


def test_dashboard_displays_empty_records():
    # Simula uma análise sem registros
    analysis_result = {
        "quality_status": "SEM DADOS",
        "summary": {
            "total_records": 0,
            "valid_records": 0,
            "invalid_records": 0,
            "total_issues": 0,
            "valid_percentage": None,
        },
    }

    # Simula a API conectada
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"status": "ok"}

        # Inicializa o dashboard
        app = AppTest.from_file(str(APP_PATH))

        # Insere os resultados simulados na sessão
        app.session_state["analysis_result"] = analysis_result

        # Executa a aplicação
        app.run(timeout=10)

    # Verifica se não ocorreram exceções
    assert not app.exception

    # Recupera os indicadores apresentados
    metrics = {metric.label: str(metric.value) for metric in app.main.metric}

    # Confere os valores esperados
    assert metrics["Total de registros"] == "0"
    assert metrics["Registros válidos"] == "0"
    assert metrics["Registros inválidos"] == "0"
    assert metrics["Taxa de validade"] == "N/D"

    # Confere as mensagens exibidas
    info_messages = [message.value for message in app.main.info]

    assert any("Não há registros para analisar" in message for message in info_messages)

    assert any(
        "Não há dados suficientes para calcular a qualidade" in message
        for message in info_messages
    )

    assert any(
        "Não há registros para gerar o gráfico" in message for message in info_messages
    )


def test_dashboard_upload_and_analyze_csv():
    # Arquivo CSV simulado
    csv_content = (
        b"id_transacao,cliente_id,valor\n"
        b"T101,C101,150.00\n"
        b"T102,C102,250.50\n"
        b"T103,C103,400.00\n"
    )

    # Resposta simulada da API
    analysis_result = {
        "quality_status": "SEM INCONSISTÊNCIAS",
        "summary": {
            "total_records": 3,
            "valid_records": 3,
            "invalid_records": 0,
            "total_issues": 0,
            "valid_percentage": 100.0,
        },
    }

    with patch("requests.get") as mock_get, patch("requests.post") as mock_post:
        # Simula a API conectada
        mock_get.return_value.json.return_value = {"status": "ok"}

        # Simula a resposta da análise
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = analysis_result

        # Abre o dashboard
        app = AppTest.from_file(str(APP_PATH)).run(timeout=10)

        # Simula o upload de um CSV
        app.file_uploader[0].upload(
            "transacoes_validas.csv",
            csv_content,
            "text/csv",
        ).run(timeout=10)

        # Simula o clique no botão
        app.button[0].click().run(timeout=10)

    # Verifica se o dashboard não apresentou erros
    assert not app.exception

    # Verifica se a API recebeu uma requisição
    mock_post.assert_called_once()

    # Verifica se o arquivo enviado está correto
    sent_file = mock_post.call_args.kwargs["files"]["file"]

    assert sent_file[0] == "transacoes_validas.csv"
    assert sent_file[1] == csv_content
    assert sent_file[2] == "text/csv"

    # Verifica os indicadores após a análise
    metrics = {metric.label: str(metric.value) for metric in app.main.metric}

    assert metrics["Total de registros"] == "3"
    assert metrics["Registros válidos"] == "3"
    assert metrics["Registros inválidos"] == "0"
    assert metrics["Taxa de validade"] == "100.00%"

    # Confere a mensagem de sucesso
    assert any(
        "Análise concluída com sucesso" in message.value for message in app.main.success
    )
