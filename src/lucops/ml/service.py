"""Server-only access to a trusted local model; no user-supplied model paths."""

import logging
import os
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from threading import Lock

from .artifacts import load_model
from .detector import analyze_transactions
from .features import prepare_csv_features

logger = logging.getLogger(__name__)
_model_lock = Lock()


class ModelUnavailableError(RuntimeError):
    """The server's configured ML artifact is unavailable."""


@lru_cache(maxsize=1)
def _load_cached_model(path: str):
    return load_model(path)


def analyze_csv_anomalies(file_path: str | Path) -> dict:
    """Use only the server environment's model, loaded once per process/path.

    Restart server workers after replacing an artifact at the same path.
    No training is performed. Missing optional dependencies are handled by API.
    """
    configured_path = os.getenv("LUCOPS_MODEL_PATH", "").strip()
    if not configured_path:
        raise ModelUnavailableError("Modelo de ML não configurado no servidor.")
    try:
        with _model_lock:
            model, metadata = _load_cached_model(str(Path(configured_path).resolve()))
    except (OSError, ValueError) as exc:
        logger.warning("Configured ML model unavailable: %s", exc)
        raise ModelUnavailableError(
            "Modelo de ML indisponível ou incompatível. Contate o administrador."
        ) from exc

    data = prepare_csv_features(file_path)
    result = analyze_transactions(model, data)
    return {
        "model_version": metadata["model_version"],
        "evaluated_records": len(result.results),
        "skipped_records": len(result.ineligible),
        "anomalies_detected": sum(record.is_anomaly for record in result.results),
        **asdict(result),
    }
