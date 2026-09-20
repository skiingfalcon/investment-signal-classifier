import json
import shutil

from typer.testing import CliRunner

from isc.cli import app

runner = CliRunner()


def _spark_repo(tmp_path, sec_data_dir):
    repo = tmp_path / "spark_repo"
    shutil.copytree(sec_data_dir, repo / "evals" / "data" / "sec")
    return repo


def test_questions_command_prints_valid_json():
    result = runner.invoke(app, ["questions"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "overall_signal" in payload


def test_facts_command_writes_a_jsonl_file(tmp_path, sec_data_dir, monkeypatch):
    repo = _spark_repo(tmp_path, sec_data_dir)
    monkeypatch.setenv("ISC_SPARK_REPO", str(repo))
    out = tmp_path / "facts.jsonl"
    result = runner.invoke(app, ["facts", "--source", "xbrl", "--years", "4", "--out", str(out)])
    assert result.exit_code == 0, result.stdout
    lines = out.read_text().splitlines()
    assert len(lines) == 6  # 4 ACME years + 2 BETA years


def test_show_command_prints_state_and_labels(tmp_path, sec_data_dir, monkeypatch):
    repo = _spark_repo(tmp_path, sec_data_dir)
    monkeypatch.setenv("ISC_SPARK_REPO", str(repo))
    result = runner.invoke(app, ["show", "ACME", "--fy", "2025-12-31"])
    assert result.exit_code == 0, result.stdout
    assert "revenue" in result.stdout
    assert "overall_signal" in result.stdout


def test_run_report_and_compare_round_trip(tmp_path, sec_data_dir, monkeypatch):
    repo = _spark_repo(tmp_path, sec_data_dir)
    monkeypatch.setenv("ISC_SPARK_REPO", str(repo))
    facts_path = tmp_path / "facts.jsonl"
    runs_dir = tmp_path / "runs"
    assert (
        runner.invoke(
            app, ["facts", "--source", "xbrl", "--years", "4", "--out", str(facts_path)]
        ).exit_code
        == 0
    )
    monkeypatch.setenv("ISC_RUNS_DIR", str(runs_dir))

    result = runner.invoke(
        app, ["run", "--backend", "mock", "--facts-path", str(facts_path), "--no-escalate"]
    )
    assert result.exit_code == 0, result.stdout
    run_dirs = list(runs_dir.iterdir())
    assert len(run_dirs) == 1

    report_result = runner.invoke(app, ["report", str(run_dirs[0]), "--markdown"])
    assert report_result.exit_code == 0
    assert "Per-question accuracy" in report_result.stdout

    compare_result = runner.invoke(
        app, ["compare", str(run_dirs[0]), str(run_dirs[0]), "--markdown"]
    )
    assert compare_result.exit_code == 0
    assert compare_result.stdout.count(run_dirs[0].name) == 2


def test_jev_classify_refuses_experimental_model_without_the_flag():
    result = runner.invoke(
        app, ["jev", "classify", "examples/bicycle.json", "--model", "gpt-oss-120b"]
    )
    assert result.exit_code != 0


def test_run_with_typesafe_backend_fails_fast_without_either_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    facts_path = tmp_path / "facts.jsonl"
    facts_path.write_text("")  # backend construction is checked before any facts are needed
    result = runner.invoke(app, ["run", "--backend", "typesafe", "--facts-path", str(facts_path)])
    assert result.exit_code != 0
    assert "TYPESAFE_API_KEY" in result.output
    assert "OPENROUTER_API_KEY" in result.output
