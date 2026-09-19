from isc.rules import label_from_values


def L(current, prior):
    return label_from_values(current, prior)


def test_revenue_growth_boundaries():
    assert L({"revenue": 103.0}, {"revenue": 100.0})["revenue_growth"] == "growing"  # +3.0%
    assert L({"revenue": 97.0}, {"revenue": 100.0})["revenue_growth"] == "declining"  # -3.0%
    assert L({"revenue": 102.9}, {"revenue": 100.0})["revenue_growth"] == "flat"
    assert L({"revenue": 97.1}, {"revenue": 100.0})["revenue_growth"] == "flat"
    assert L({}, {"revenue": 100.0})["revenue_growth"] == "other"
    assert L({"revenue": 100.0}, {})["revenue_growth"] == "other"


def test_profitability_trend_loss_making_takes_precedence():
    # Net income negative wins even though the YoY change looks like "improving" (-5 vs -50).
    assert L({"net_income": -5.0}, {"net_income": -50.0})["profitability_trend"] == "loss_making"


def test_profitability_trend_boundaries():
    assert L({"net_income": 105.0}, {"net_income": 100.0})["profitability_trend"] == "improving"
    assert L({"net_income": 95.0}, {"net_income": 100.0})["profitability_trend"] == "deteriorating"
    assert L({"net_income": 102.0}, {"net_income": 100.0})["profitability_trend"] == "stable"
    assert L({}, {"net_income": 100.0})["profitability_trend"] == "other"


def test_ocf_covers_net_income():
    assert (
        L({"operating_cash_flow": 100.0, "net_income": 100.0}, {})["ocf_covers_net_income"] is True
    )
    assert (
        L({"operating_cash_flow": 99.0, "net_income": 100.0}, {})["ocf_covers_net_income"] is False
    )
    assert L({"net_income": 100.0}, {})["ocf_covers_net_income"] is None


def test_eps_increased():
    assert L({"eps_diluted": 1.01}, {"eps_diluted": 1.00})["eps_increased"] is True
    assert L({"eps_diluted": 1.00}, {"eps_diluted": 1.00})["eps_increased"] is False
    assert L({}, {"eps_diluted": 1.00})["eps_increased"] is None


def test_leverage_boundaries_and_special_cases():
    assert L({"equity": -1.0, "long_term_debt": 10.0}, {})["leverage"] == 2  # negative equity
    assert L({"equity": 100.0, "long_term_debt": 0.0}, {})["leverage"] == 0  # no debt
    assert L({"equity": 100.0, "long_term_debt": 49.0}, {})["leverage"] == 0
    assert L({"equity": 100.0, "long_term_debt": 50.0}, {})["leverage"] == 1
    assert L({"equity": 100.0, "long_term_debt": 200.0}, {})["leverage"] == 1
    assert L({"equity": 100.0, "long_term_debt": 201.0}, {})["leverage"] == 2
    assert L({"equity": 100.0}, {})["leverage"] is None


def test_liquidity_boundaries():
    assert L({"cash": 50.0, "long_term_debt": 0.0}, {})["liquidity"] == "strong"
    assert L({"cash": 100.0, "long_term_debt": 100.0}, {})["liquidity"] == "strong"
    assert L({"cash": 25.0, "long_term_debt": 100.0}, {})["liquidity"] == "adequate"
    assert L({"cash": 24.0, "long_term_debt": 100.0}, {})["liquidity"] == "thin"
    assert L({"long_term_debt": 100.0}, {})["liquidity"] == "other"


def test_share_count_boundaries():
    assert (
        L({"shares_outstanding": 99.0}, {"shares_outstanding": 100.0})["share_count"] == "buyback"
    )
    assert (
        L({"shares_outstanding": 101.0}, {"shares_outstanding": 100.0})["share_count"] == "dilution"
    )
    assert (
        L({"shares_outstanding": 100.5}, {"shares_outstanding": 100.0})["share_count"] == "stable"
    )
    assert L({}, {"shares_outstanding": 100.0})["share_count"] == "other"


def test_overall_signal_precedence():
    growing = {"revenue": 106.0, "net_income": 106.0, "eps_diluted": 1.1}
    prior = {"revenue": 100.0, "net_income": 100.0, "eps_diluted": 1.0}
    assert L(growing, prior)["overall_signal"] == "bullish"

    # Net income negative forces bearish even with strong revenue growth.
    bearish_case = {"revenue": 120.0, "net_income": -1.0, "eps_diluted": 1.1}
    assert L(bearish_case, prior)["overall_signal"] == "bearish"

    neutral_case = {"revenue": 101.0, "net_income": 101.0, "eps_diluted": 1.01}
    assert L(neutral_case, prior)["overall_signal"] == "neutral"

    assert L({"net_income": 100.0}, {})["overall_signal"] == "other"  # revenue pct missing
    # Not bearish, revenue/NI both grow enough, but EPS comparison unavailable -> other.
    missing_eps = {"revenue": 106.0, "net_income": 106.0}
    assert L(missing_eps, prior)["overall_signal"] == "other"


def test_rule_keys_cover_every_question():
    from isc.rules import RULE_KEYS

    result = L({}, {})
    assert set(result) == set(RULE_KEYS)
