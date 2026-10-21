import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pytest
import sklearn
from sklearn.ensemble import IsolationForest

from lucops.ml.artifacts import load_model, save_model
from lucops.ml.schemas import PreparedTransactions, TransactionFeatures
from lucops.ml.training import train_detector


@pytest.fixture
def model():
    data = PreparedTransactions(
        tuple(TransactionFeatures(i, str(i), str(i), float(i)) for i in range(1, 30)),
        (),
    )
    return train_detector(data)


def test_round_trip_preserves_predictions_and_metadata(tmp_path, model):
    path = tmp_path / "models" / "test.joblib"
    metadata = save_model(model, path, model_version="experiment-1")
    restored, loaded_metadata = load_model(path)
    assert loaded_metadata == metadata
    assert metadata["model_version"] == "experiment-1"
    assert metadata["features"] == ["valor"]
    assert metadata["training_records"] == 29
    assert metadata["sklearn_version"] == sklearn.__version__
    assert metadata["training_parameters"] == model.get_params()
    np.testing.assert_array_equal(
        model.decision_function([[10], [1000]]),
        restored.decision_function([[10], [1000]]),
    )


@pytest.mark.parametrize("missing", ["model", "metadata"])
def test_missing_artifact_files(tmp_path, model, missing):
    path = tmp_path / "test.joblib"
    save_model(model, path)
    (path if missing == "model" else Path(str(path) + ".json")).unlink()
    with pytest.raises(FileNotFoundError, match="not found"):
        load_model(path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("artifact_format", 99),
        ("producer", "unknown"),
        ("features", ["cliente_id"]),
        ("sklearn_version", "0.0"),
        ("algorithm", "Other"),
        ("model_version", ""),
        ("training_records", True),
        ("training_records", 1),
        ("training_parameters", []),
        ("sha256", "invalid"),
    ],
)
def test_rejects_invalid_metadata_before_deserialization(tmp_path, model, field, value):
    path = tmp_path / "test.joblib"
    save_model(model, path)
    sidecar = Path(str(path) + ".json")
    metadata = json.loads(sidecar.read_text())
    metadata[field] = value
    sidecar.write_text(json.dumps(metadata))
    with patch("lucops.ml.artifacts.joblib.load") as deserialize:
        with pytest.raises(ValueError, match="metadata"):
            load_model(path)
        deserialize.assert_not_called()


@pytest.mark.parametrize("contents", ["not-json", "[]", "{}"])
def test_corrupted_or_incomplete_metadata(tmp_path, model, contents):
    path = tmp_path / "test.joblib"
    save_model(model, path)
    Path(str(path) + ".json").write_text(contents)
    with pytest.raises(ValueError, match="metadata"):
        load_model(path)


def test_checksum_rejected_before_deserialization(tmp_path, model):
    path = tmp_path / "test.joblib"
    save_model(model, path)
    path.write_bytes(b"broken")
    with patch("lucops.ml.artifacts.joblib.load") as deserialize:
        with pytest.raises(ValueError, match="checksum"):
            load_model(path)
        deserialize.assert_not_called()


@pytest.mark.parametrize(
    "kind", ["corrupted", "wrong_type", "unfitted", "count", "params"]
)
def test_corrupted_or_incompatible_payload(tmp_path, model, kind):
    path = tmp_path / "test.joblib"
    metadata = save_model(model, path)
    if kind == "corrupted":
        path.write_bytes(b"not a joblib model")
    elif kind == "wrong_type":
        joblib.dump({"unexpected": "object"}, path)
    elif kind == "unfitted":
        joblib.dump(IsolationForest(), path)
    elif kind == "count":
        metadata["training_records"] += 1
    else:
        metadata["training_parameters"]["n_estimators"] += 1
    metadata["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    Path(str(path) + ".json").write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="Corrupted or incompatible"):
        load_model(path)


def test_save_refuses_overwrite_and_invalid_version(tmp_path, model):
    path = tmp_path / "test.joblib"
    with pytest.raises(ValueError, match="model_version"):
        save_model(model, path, model_version="")
    assert not path.exists()
    save_model(model, path)
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        save_model(model, path)
    assert path.read_bytes() == original


def test_save_rejects_unfitted_or_external_model(tmp_path):
    with pytest.raises(ValueError):
        save_model(IsolationForest(), tmp_path / "unfitted.joblib")
    external = IsolationForest(random_state=42).fit([[1], [2]])
    with pytest.raises(ValueError, match="train_detector"):
        save_model(external, tmp_path / "external.joblib")
