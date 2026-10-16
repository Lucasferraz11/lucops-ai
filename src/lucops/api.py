from dataclasses import asdict
from pathlib import Path
from shutil import copyfileobj
from tempfile import TemporaryDirectory
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile

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
