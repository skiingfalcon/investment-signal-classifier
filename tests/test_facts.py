import json
import math

from isc import facts as facts_module


def test_xbrl_factsets_newest_first_with_priors(sec_data_dir):
    raw = json.loads((sec_data_dir / "ACME" / "companyfacts.json").read_text())
    fsets = facts_module.xbrl_factsets(raw, "ACME", years=5)
    assert [fs.fiscal_year_end for fs in fsets] == [
        "2026-12-31",
        "2025-12-31",
        "2024-12-31",
        "2023-12-31",
    ]
    assert fsets[0].prior_year_end == "2025-12-31"
    assert fsets[-1].prior_year_end is None  # oldest year has no prior in this fixture
    assert fsets[-1].prior == {}


def test_derived_ratios_for_a_clean_growth_year(sec_data_dir):
    raw = json.loads((sec_data_dir / "ACME" / "companyfacts.json").read_text())
    fs = facts_module.xbrl_factset(raw, "ACME", "2025-12-31", "2024-12-31")
    assert math.isclose(fs.ratios.revenue_yoy, (1250.0 - 1100.0) / 1100.0)
    assert math.isclose(fs.ratios.net_income_yoy, (150.0 - 120.0) / 120.0)
    assert math.isclose(fs.ratios.debt_to_equity, 350.0 / 1200.0)
    assert math.isclose(fs.ratios.cash_to_debt, 500.0 / 350.0)
    assert fs.quality.negative_equity is False
    assert fs.quality.no_long_term_debt is False


def test_coverage_gap_year_lists_missing_current(sec_data_dir):
    raw = json.loads((sec_data_dir / "ACME" / "companyfacts.json").read_text())
    fs = facts_module.xbrl_factset(raw, "ACME", "2026-12-31", "2025-12-31")
    assert set(fs.quality.missing_current) == {
        "operating_income",
        "long_term_debt",
        "shares_outstanding",
    }


def test_negative_equity_and_zero_debt_flags(sec_data_dir):
    raw = json.loads((sec_data_dir / "BETA" / "companyfacts.json").read_text())
    loss_year = facts_module.xbrl_factset(raw, "BETA", "2025-06-30", "2024-06-30")
    assert loss_year.quality.negative_equity is True
    assert loss_year.ratios.debt_to_equity is None

    prior_year = facts_module.xbrl_factset(raw, "BETA", "2024-06-30", None)
    assert prior_year.quality.no_long_term_debt is True
    assert prior_year.ratios.cash_to_debt is None


def test_model_factsets_reads_current_from_run_and_prior_from_xbrl(sec_data_dir, results_mini_path):
    fsets = facts_module.model_factsets(results_mini_path, sec_data_dir, run_name="test-run")
    by_ticker = {fs.ticker: fs for fs in fsets}
    assert set(by_ticker) == {"ACME", "BETA"}  # the 10-Q row must not create a third group

    acme = by_ticker["ACME"]
    assert acme.source == "model:test-run"
    assert acme.prior_year_end == "2024-12-31"
    assert acme.current["revenue"].value == 1250.0e6
    assert acme.current["revenue"].source == "model"
    assert acme.prior["revenue"].source == "xbrl"
    assert "net_income" in acme.quality.model_wrong
    assert "net_income" in acme.quality.off_by_scale
    assert acme.quality.missing_current == ["operating_cash_flow"]
    assert acme.current["net_income"].correct is False
    assert acme.current["net_income"].expected == 150.0e6

    beta = by_ticker["BETA"]
    assert beta.prior_year_end == "2024-06-30"
    assert beta.current["operating_cash_flow"].value == 10.0e6  # sign-flipped, as scored wrong
    assert "operating_cash_flow" in beta.quality.model_wrong


def test_xbrl_twin_reconstructs_ground_truth_for_a_model_factset(sec_data_dir, results_mini_path):
    fsets = facts_module.model_factsets(results_mini_path, sec_data_dir, run_name="test-run")
    acme_model = next(fs for fs in fsets if fs.ticker == "ACME")
    twin = facts_module.xbrl_twin(acme_model, sec_data_dir)
    assert twin.source == "xbrl"
    assert twin.current["net_income"].value == 150.0e6  # true value, not the model's 150000.0e6
    assert facts_module.xbrl_twin(twin, sec_data_dir) is twin  # already xbrl: returned as-is


def test_write_read_facts_round_trip(tmp_path, sec_data_dir):
    raw = json.loads((sec_data_dir / "ACME" / "companyfacts.json").read_text())
    fsets = facts_module.xbrl_factsets(raw, "ACME", years=2)
    path = tmp_path / "facts.jsonl"
    facts_module.write_facts(path, fsets)
    restored = facts_module.read_facts(path)
    assert restored == fsets
