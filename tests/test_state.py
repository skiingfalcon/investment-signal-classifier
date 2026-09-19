from isc.facts import FactSet, FactValue, derive
from isc.state import render, state_hash


def _factset() -> FactSet:
    current_raw = {
        "revenue": 1_250_000_000.0,
        "net_income": 150_000_000.0,
        "eps_diluted": 1.55,
        "operating_cash_flow": 160_000_000.0,
        "equity": 1_200_000_000.0,
        "long_term_debt": 350_000_000.0,
        "cash": 500_000_000.0,
        "shares_outstanding": 95_000_000.0,
    }
    prior_raw = {
        "revenue": 1_100_000_000.0,
        "net_income": 120_000_000.0,
        "eps_diluted": 1.20,
        "operating_cash_flow": 130_000_000.0,
        "shares_outstanding": 98_000_000.0,
    }
    ratios, quality = derive(current_raw, prior_raw)
    quality.missing_current = ["operating_income"]
    quality.missing_prior = [
        "operating_income",
        "equity",
        "long_term_debt",
        "cash",
        "total_assets",
        "total_liabilities",
    ]
    current = {k: FactValue(value=v, source="xbrl") for k, v in current_raw.items()}
    prior = {k: FactValue(value=v, source="xbrl") for k, v in prior_raw.items()}
    return FactSet(
        id="ACME:FY2025-12-31:xbrl",
        ticker="ACME",
        fiscal_year_end="2025-12-31",
        prior_year_end="2024-12-31",
        source="xbrl",
        current=current,
        prior=prior,
        ratios=ratios,
        quality=quality,
    )


def test_derived_state_scales_and_precomputes():
    state = render(_factset(), "derived")
    assert state["current"]["revenue"] == 1250.0  # USD millions, 1 decimal
    assert state["current"]["eps_diluted"] == 1.55  # per-share, not scaled
    assert state["current"]["shares_outstanding"] == 95.0  # shares in millions
    assert state["change_pct"]["revenue"] == round((1250.0 - 1100.0) / 1100.0 * 100.0, 1)
    assert "net_margin_pct" in state["ratios"]
    assert "current.operating_income" in state["not_reported"]
    assert "prior.equity" in state["not_reported"]


def test_raw_state_omits_derived_blocks():
    state = render(_factset(), "raw")
    assert "change_pct" not in state
    assert "ratios" not in state
    assert state["current"]["revenue"] == 1250.0  # values still scaled the same way


def test_state_hash_is_deterministic_and_order_independent():
    state = render(_factset(), "derived")
    h1 = state_hash(state)
    reordered = dict(reversed(list(state.items())))
    assert state_hash(reordered) == h1
    assert h1 == state_hash(render(_factset(), "derived"))
