import json

from isc import xbrl


def _load(sec_data_dir, ticker):
    return json.loads((sec_data_dir / ticker / "companyfacts.json").read_text())


def test_fiscal_year_ends_newest_first(sec_data_dir):
    facts = _load(sec_data_dir, "ACME")
    assert xbrl.fiscal_year_ends(facts) == ["2026-12-31", "2025-12-31", "2024-12-31", "2023-12-31"]


def test_select_fact_prefers_latest_filed_restatement(sec_data_dir):
    facts = _load(sec_data_dir, "ACME")
    tag = xbrl.TAG_BY_KEY["net_income"]
    fact = xbrl.select_fact(facts, tag, report_date="2023-12-31")
    assert fact["val"] == 99.0e6  # the later-filed restated value, not the original 100.0e6


def test_select_fact_resolves_alias_only_concept(sec_data_dir):
    facts = _load(sec_data_dir, "BETA")
    tag = xbrl.TAG_BY_KEY["revenue"]
    fact = xbrl.select_fact(facts, tag, report_date="2025-06-30")
    assert fact is not None
    assert fact["concept"] == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert fact["val"] == 470.0e6


def test_resolve_year_reports_coverage_gaps(sec_data_dir):
    facts = _load(sec_data_dir, "ACME")
    resolved = xbrl.resolve_year(facts, "2026-12-31")
    assert "operating_income" not in resolved  # not reported that year, like real 10-Ks
    assert "long_term_debt" not in resolved
    assert resolved["revenue"].value == 1180.0e6


def test_select_fact_missing_period_returns_none(sec_data_dir):
    facts = _load(sec_data_dir, "ACME")
    tag = xbrl.TAG_BY_KEY["revenue"]
    assert xbrl.select_fact(facts, tag, report_date="1999-01-01") is None
