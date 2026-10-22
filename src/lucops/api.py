import csv
from dataclasses import asdict
from pathlib import Path
from shutil import copyfileobj
from tempfile import TemporaryDirectory
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from .application import analyze_csv
from .rules import is_positive_amount
from .status import get_quality_status

app = FastAPI(
    title="LucOps AI",
    description="API de qualidade e análise de dados empresariais",
    version="0.1.0",
)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "LucOps AI",
    }


@app.post("/analyses")
def create_analysis(
    file: Annotated[UploadFile, File()],
) -> dict[str, object]:
    """Analyze an uploaded CSV file."""

    with TemporaryDirectory() as temporary_dir:
        directory = Path(temporary_dir)

        csv_path = directory / "transacoes.csv"
        report_path = directory / "quality_report.txt"

        with csv_path.open("wb") as destination:
            copyfileobj(file.file, destination)

        try:
            result = analyze_csv(
                file_path=csv_path,
                output_path=report_path,
                required_columns=[
                    "id_transacao",
                    "cliente_id",
                    "valor",
                ],
                rules={"valor": is_positive_amount},
                unique_fields=["id_transacao"],
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"CSV inválido: {exc}",
            ) from exc

    return {
        "quality_status": get_quality_status(result.summary),
        "summary": asdict(result.summary),
    }


@app.post(
    "/anomaly-analyses",
    responses={
        400: {"description": "Invalid CSV"},
        503: {"description": "Server ML model unavailable"},
    },
)
def create_anomaly_analysis(
    file: Annotated[UploadFile, File()],
) -> dict[str, object]:
    """Infer anomalies using only the trusted model configured on the server."""
    # Keep the traditional API usable without the optional ML dependencies.
    try:
        from .ml.service import ModelUnavailableError, analyze_csv_anomalies
    except ImportError as exc:
        raise HTTPException(
            status_code=503, detail="Dependências de ML indisponíveis no servidor."
        ) from exc

    with TemporaryDirectory() as temporary_dir:
        csv_path = Path(temporary_dir) / "transactions.csv"
        with csv_path.open("wb") as destination:
            copyfileobj(file.file, destination)
        try:
            return analyze_csv_anomalies(csv_path)
        except ModelUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (ValueError, csv.Error) as exc:
            raise HTTPException(status_code=400, detail=f"CSV inválido: {exc}") from exc


@app.post("/investigations")
def create_investigation(
    file: Annotated[UploadFile, File()],
    record_index: Annotated[int, Form()],
    provider: Annotated[Literal["simulated", "openai"], Form()] = "simulated",
) -> dict[str, object]:
    """Investigate one uploaded record; all facts are computed on the server."""
    from .agents.openai_provider import (
        OpenAIProviderError,
        OpenAIProviderResponseError,
    )
    from .agents.service import investigate_transaction
    from .ingestion import load_csv

    if record_index < 1:
        raise HTTPException(status_code=422, detail="O índice deve ser positivo.")
    with TemporaryDirectory() as temporary_dir:
        csv_path = Path(temporary_dir) / "transactions.csv"
        with csv_path.open("wb") as destination:
            copyfileobj(file.file, destination)
        try:
            records = load_csv(
                csv_path,
                required_columns=("id_transacao", "cliente_id", "valor"),
            )
        except (ValueError, csv.Error, UnicodeError) as exc:
            raise HTTPException(status_code=400, detail="CSV inválido.") from exc
        if record_index > len(records):
            raise HTTPException(
                status_code=404, detail="Transação não encontrada no CSV."
            )
        try:
            result = investigate_transaction(
                csv_path, record_index, provider_mode=provider
            )
        except IndexError as exc:
            raise HTTPException(
                status_code=404, detail="Transação não encontrada no CSV."
            ) from exc
        except OpenAIProviderResponseError as exc:
            raise HTTPException(
                status_code=502, detail="Resposta do provedor de investigação inválida."
            ) from exc
        except OpenAIProviderError as exc:
            raise HTTPException(
                status_code=503, detail="Provedor de investigação indisponível."
            ) from exc
        except (ValueError, csv.Error, UnicodeError) as exc:
            raise HTTPException(
                status_code=500, detail="Falha interna na investigação."
            ) from exc
    return asdict(result)
