import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from lucops.agents import openai_provider
from lucops.agents.__main__ import main

HEADER = "id_transacao,cliente_id,valor\n"


def write_csv(tmp_path, rows):
    path = tmp_path / "input.csv"
    path.write_text(HEADER + rows, encoding="utf-8")
    return path


def run_cli(*arguments):
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
    }
    env.pop("LUCOPS_MODEL_PATH", None)
    return subprocess.run(
        [sys.executable, "-m", "lucops.agents", *map(str, arguments)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def test_independent_cli_outputs_complete_simulated_investigation(tmp_path):
    path = write_csv(tmp_path, "PRIVATE,C1,-20\n")
    output = tmp_path / "reports" / "investigation.json"
    original = path.read_bytes()
    process = run_cli(
        "investigate",
        path,
        "--record-index",
        1,
        "--no-ml",
        "--output",
        output,
    )
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result == json.loads(output.read_text(encoding="utf-8"))
    assert result["mode"] == "simulated"
    assert result["context"]["record_index"] == 1
    assert result["hypotheses"][0]["status"] == "unconfirmed"
    assert result["actions_executed"] is False
    assert result["verified_evidence"]
    assert result["insufficient_evidence"]
    assert "PRIVATE" not in process.stdout
    assert path.read_bytes() == original


def test_cli_reports_unavailable_ml_without_a_model(tmp_path):
    process = run_cli(
        "investigate",
        write_csv(tmp_path, "A,C1,100\n"),
        "--record-index",
        1,
    )
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result["context"]["ml"]["status"] == "unavailable"
    assert result["context"]["ml"]["is_anomaly"] is None
    assert any(
        "ausência de pontuação" in text for text in result["insufficient_evidence"]
    )


@pytest.mark.parametrize(
    "scenario",
    [
        "missing_file",
        "invalid_csv",
        "zero_index",
        "missing_record",
        "empty_dataset",
    ],
)
def test_cli_clear_errors_without_partial_json(tmp_path, capsys, scenario):
    path = write_csv(tmp_path, "A,C1,100\n")
    index = "1"
    if scenario == "missing_file":
        path.unlink()
    elif scenario == "invalid_csv":
        path.write_text("wrong\nvalue\n")
    elif scenario == "zero_index":
        index = "0"
    elif scenario == "missing_record":
        index = "2"
    else:
        path.write_text(HEADER)
    with pytest.raises(SystemExit) as error:
        main(["investigate", str(path), "--record-index", index, "--no-ml"])
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert captured.out == ""


@pytest.mark.parametrize(
    "arguments", [[], ["investigate"], ["investigate", "input.csv"]]
)
def test_cli_required_arguments(arguments, capsys):
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2
    capsys.readouterr()


def test_cli_refuses_to_overwrite_existing_output(tmp_path, capsys):
    path = write_csv(tmp_path, "A,C1,-20\n")
    output = tmp_path / "existing.json"
    output.write_text("keep")
    with pytest.raises(SystemExit):
        main(
            [
                "investigate",
                str(path),
                "--record-index",
                "1",
                "--no-ml",
                "--output",
                str(output),
            ]
        )
    assert output.read_text() == "keep"
    assert capsys.readouterr().out == ""


def test_cli_cannot_overwrite_input_csv(tmp_path, capsys):
    path = write_csv(tmp_path, "A,C1,-20\n")
    original = path.read_bytes()
    with pytest.raises(SystemExit):
        main(
            [
                "investigate",
                str(path),
                "--record-index",
                "1",
                "--no-ml",
                "--output",
                str(path),
            ]
        )
    assert path.read_bytes() == original
    capsys.readouterr()


def test_cli_explicit_simulated_provider_preserves_offline_mode(tmp_path):
    process = run_cli(
        "investigate",
        write_csv(tmp_path, "A,C1,100\n"),
        "--record-index",
        1,
        "--provider",
        "simulated",
        "--no-ml",
    )
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)["mode"] == "simulated"


def test_cli_openai_without_key_fails_without_partial_json(
    tmp_path, capsys, monkeypatch
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = lambda _key: pytest.fail("Client must not be created without a key")
    monkeypatch.setattr(openai_provider, "_make_client", client)
    with pytest.raises(SystemExit) as error:
        main(
            [
                "investigate",
                str(write_csv(tmp_path, "A,C1,100\n")),
                "--record-index",
                "1",
                "--provider",
                "openai",
                "--no-ml",
            ]
        )
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "OPENAI_API_KEY" in captured.err


def test_cli_rejects_unknown_provider_without_a_call(tmp_path):
    process = run_cli(
        "investigate",
        write_csv(tmp_path, "A,C1,100\n"),
        "--record-index",
        1,
        "--provider",
        "other",
        "--no-ml",
    )
    assert process.returncode == 2
    assert process.stdout == ""
    assert "invalid choice" in process.stderr
