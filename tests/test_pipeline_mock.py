import json
import shutil

from isc import facts as facts_module
from isc import pipeline
from isc.backends import MockBackend
from isc.config import Settings
from isc.policy import Route


def _factsets(sec_data_dir):
    acme = json.loads((sec_data_dir / "ACME" / "companyfacts.json").read_text())
    beta = json.loads((sec_data_dir / "BETA" / "companyfacts.json").read_text())
    return facts_module.xbrl_factsets(acme, "ACME", years=4) + facts_module.xbrl_factsets(
        beta, "BETA", years=2
    )


def test_noiseless_mock_run_is_all_auto_and_fully_accurate(tmp_path, sec_data_dir):
    settings = Settings(spark_repo=tmp_path, runs_dir=tmp_path / "runs")
    settings.sec_data_dir.parent.mkdir(parents=True, exist_ok=True)
    factsets = _factsets(sec_data_dir)
    run_dir = pipeline.run(
        settings,
        backend=MockBackend(noise=0.0),
        arbiter=None,
        factsets=factsets,
        verify=True,
        escalate=False,
    )
    assert (run_dir / "results.jsonl").is_file()
    assert (run_dir / "run.json").is_file()
    assert (run_dir / "report.md").is_file()

    rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text().splitlines()]
    assert len(rows) == len(factsets)
    for row in rows:
        assert row["decision"]["route"] == Route.AUTO.value
        for qid, outcome in row["decision"]["outcomes"].items():
            truth = row["labels"]["truth"].get(qid)
            if truth not in (None, "other"):
                assert outcome["final"] == truth, (row["id"], qid)


def test_noisy_mock_run_produces_verified_and_review_routes(tmp_path, sec_data_dir):
    # With 8 questions per row, noise=0.6 makes an all-questions-agree (auto) row exceedingly
    # unlikely; the interesting assertion is that low-confidence disagreements get resolved by
    # stage 2 (verified) or, failing that, fall to review -- never silently escalated with no
    # arbiter configured.
    settings = Settings(spark_repo=tmp_path, runs_dir=tmp_path / "runs")
    factsets = _factsets(sec_data_dir) * 3
    run_dir = pipeline.run(
        settings,
        backend=MockBackend(noise=0.6, seed=7),
        arbiter=None,
        factsets=factsets,
        verify=True,
        escalate=False,
    )
    run_meta = json.loads((run_dir / "run.json").read_text())
    assert run_meta["routes"].get("verified", 0) > 0
    assert run_meta["routes"].get("review", 0) > 0
    assert sum(run_meta["routes"].values()) == len(factsets)
    # No arbiter configured: unresolved disputes fall to review, never escalated.
    assert run_meta["routes"].get("escalated", 0) == 0


def test_low_noise_mock_run_still_produces_some_auto_rows(tmp_path, sec_data_dir):
    settings = Settings(spark_repo=tmp_path, runs_dir=tmp_path / "runs")
    factsets = _factsets(sec_data_dir) * 3
    run_dir = pipeline.run(
        settings,
        backend=MockBackend(noise=0.05, seed=3),
        arbiter=None,
        factsets=factsets,
        verify=True,
        escalate=False,
    )
    run_meta = json.loads((run_dir / "run.json").read_text())
    assert run_meta["routes"].get("auto", 0) > 0


def test_extraction_impact_flags_model_rows_where_extraction_changed_a_label(
    tmp_path, sec_data_dir, results_mini_path
):
    settings = Settings(spark_repo=tmp_path, runs_dir=tmp_path / "runs")
    shutil.copytree(
        sec_data_dir, settings.sec_data_dir, dirs_exist_ok=True
    )  # xbrl_twin() needs this on disk
    factsets = facts_module.model_factsets(results_mini_path, sec_data_dir, run_name="test-run")
    run_dir = pipeline.run(
        settings,
        backend=MockBackend(noise=0.0),
        arbiter=None,
        factsets=factsets,
        verify=True,
        escalate=False,
    )
    rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text().splitlines()]
    acme_row = next(r for r in rows if r["ticker"] == "ACME")
    # The scaled-by-1000 net_income extraction error changes profitability_trend/overall_signal.
    assert acme_row["labels"]["extraction_changed_label"]
    report_text = (run_dir / "report.md").read_text()
    assert "Extraction impact" in report_text
