import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from sklearn.ensemble import IsolationForest

from lucops.ml.__main__ import main


def csv_file(tmp_path, rows):
    path = tmp_path / "input.csv"
    path.write_text("id_transacao,cliente_id,valor\n" + rows, encoding="utf-8")
    return path


def run_cli(*args):
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    return subprocess.run(
        [sys.executable, "-m", "lucops.ml", *map(str, args)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def test_commands_work_in_separate_processes(tmp_path):
    historical = csv_file(tmp_path, "A,C1,100\nB,C2,200\nC,,-1\n")
    model = tmp_path / "models" / "test.joblib"
    trained = run_cli("train", historical, "--model", model, "--model-version", "demo")
    assert trained.returncode == 0, trained.stderr
    metadata = json.loads(trained.stdout)
    assert metadata["metadata"]["training_records"] == 2
    assert metadata["skipped_records"] == 1
    original_model = model.read_bytes()
    new_data = tmp_path / "new.csv"
    new_data.write_text(
        "id_transacao,cliente_id,valor\nNEW,C1,1000000\nBAD,,0\n",
        encoding="utf-8",
    )
    output = tmp_path / "reports" / "result.json"
    analyzed = run_cli("analyze", new_data, "--model", model, "--output", output)
    assert analyzed.returncode == 0, analyzed.stderr
    result = json.loads(output.read_text())
    assert result == json.loads(analyzed.stdout)
    assert result["model_version"] == "demo"
    assert result["evaluated_records"] == 1
    assert result["skipped_records"] == 1
    assert result["results"][0]["transaction_id"] == "NEW"
    assert result["ineligible"][0]["issues"]
    assert model.read_bytes() == original_model


def test_analyze_never_trains_and_handles_empty_input(tmp_path, capsys):
    path = csv_file(tmp_path, "A,C1,100\nB,C2,200\n")
    model = tmp_path / "model.joblib"
    main(["train", str(path), "--model", str(model)])
    capsys.readouterr()
    path.write_text("id_transacao,cliente_id,valor\n")
    with patch.object(
        IsolationForest, "fit", side_effect=AssertionError("No training")
    ):
        main(["analyze", str(path), "--model", str(model)])
    assert json.loads(capsys.readouterr().out)["results"] == []


@pytest.mark.parametrize(
    "scenario", ["missing_csv", "invalid_csv", "too_few", "missing_model"]
)
def test_cli_clear_errors(tmp_path, capsys, scenario):
    path = csv_file(tmp_path, "A,C1,100\n")
    model = tmp_path / "missing.joblib"
    command = "train"
    if scenario == "missing_csv":
        path.unlink()
    elif scenario == "invalid_csv":
        path.write_text("wrong\nvalue\n")
    elif scenario == "missing_model":
        command = "analyze"
    with pytest.raises(SystemExit) as error:
        main([command, str(path), "--model", str(model)])
    assert error.value.code == 2
    assert "error:" in capsys.readouterr().err
    assert not model.exists()


def test_existing_output_is_not_overwritten(tmp_path, capsys):
    path = csv_file(tmp_path, "A,C1,100\nB,C2,200\n")
    model = tmp_path / "model.joblib"
    main(["train", str(path), "--model", str(model)])
    output = tmp_path / "result.json"
    output.write_text("keep")
    with pytest.raises(SystemExit):
        main(["analyze", str(path), "--model", str(model), "--output", str(output)])
    assert output.read_text() == "keep"
    capsys.readouterr()


def test_train_cannot_overwrite_csv(tmp_path):
    path = csv_file(tmp_path, "A,C1,100\nB,C2,200\n")
    before = path.read_bytes()
    with pytest.raises(SystemExit):
        main(["train", str(path), "--model", str(path)])
    assert path.read_bytes() == before
