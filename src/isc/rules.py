"""The deterministic rule engine: the arithmetic ground truth JEV is checked against.

This is the only place threshold numbers live. ``questions.py`` renders its criteria text from
these same constants so the prompt and the rulebook cannot drift apart.

The core logic (``label_from_values``) works on plain ``{key: float}`` dicts of current/prior
values, not on :class:`isc.facts.FactSet` directly. That lets ``isc.backends.MockBackend`` derive
the same labels straight from a rendered ``state`` dict (whose ``current``/``prior`` blocks carry
the same values, just unit-scaled) without depending on FactSet or re-deriving ratios: every
threshold here is either a percent change or a ratio, both scale-invariant.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from isc.facts import FactSet

THRESHOLDS: dict[str, float] = {
    "revenue_pct": 3.0,
    "net_income_pct": 5.0,
    "share_pct": 1.0,
    "de_low": 0.5,
    "de_high": 2.0,
    "cash_to_debt_strong": 1.0,
    "cash_to_debt_adequate": 0.25,
}

RULE_KEYS: tuple[str, ...] = (
    "revenue_growth",
    "profitability_trend",
    "ocf_covers_net_income",
    "eps_increased",
    "leverage",
    "liquidity",
    "share_count",
    "overall_signal",
)


def _pct_change(cur: float | None, prior: float | None) -> float | None:
    if cur is None or prior is None or prior == 0:
        return None
    return (cur - prior) / abs(prior) * 100.0


def _revenue_growth(revenue_pct: float | None) -> str:
    if revenue_pct is None:
        return "other"
    t = THRESHOLDS["revenue_pct"]
    if revenue_pct >= t:
        return "growing"
    if revenue_pct <= -t:
        return "declining"
    return "flat"


def _profitability_trend(net_income: float | None, net_income_pct: float | None) -> str:
    if net_income is not None and net_income < 0:
        return "loss_making"
    if net_income_pct is None:
        return "other"
    t = THRESHOLDS["net_income_pct"]
    if net_income_pct >= t:
        return "improving"
    if net_income_pct <= -t:
        return "deteriorating"
    return "stable"


def _ocf_covers_net_income(ocf: float | None, net_income: float | None) -> bool | None:
    if ocf is None or net_income is None:
        return None
    return ocf >= net_income


def _eps_increased(cur: float | None, prior: float | None) -> bool | None:
    if cur is None or prior is None:
        return None
    return cur > prior


def _leverage(equity: float | None, long_term_debt: float | None) -> int | None:
    if equity is not None and equity <= 0:
        return 2
    if long_term_debt is not None and long_term_debt == 0:
        return 0
    if equity is None or long_term_debt is None:
        return None
    de = long_term_debt / equity
    if de < THRESHOLDS["de_low"]:
        return 0
    if de <= THRESHOLDS["de_high"]:
        return 1
    return 2


def _liquidity(cash: float | None, long_term_debt: float | None) -> str:
    if long_term_debt is not None and long_term_debt == 0:
        return "strong"
    if cash is None or long_term_debt is None:
        return "other"
    ratio = cash / long_term_debt
    if ratio >= THRESHOLDS["cash_to_debt_strong"]:
        return "strong"
    if ratio >= THRESHOLDS["cash_to_debt_adequate"]:
        return "adequate"
    return "thin"


def _share_count(share_pct: float | None) -> str:
    if share_pct is None:
        return "other"
    t = THRESHOLDS["share_pct"]
    if share_pct <= -t:
        return "buyback"
    if share_pct >= t:
        return "dilution"
    return "stable"


def _overall_signal(
    net_income: float | None,
    revenue_pct: float | None,
    net_income_pct: float | None,
    eps_increased: bool | None,
) -> str:
    if revenue_pct is None or net_income_pct is None:
        return "other"
    if (
        (net_income is not None and net_income < 0)
        or net_income_pct <= -THRESHOLDS["net_income_pct"]
        or revenue_pct <= -THRESHOLDS["revenue_pct"]
    ):
        return "bearish"
    if eps_increased is None:
        return "other"
    if (
        revenue_pct >= THRESHOLDS["revenue_pct"]
        and net_income_pct >= THRESHOLDS["net_income_pct"]
        and eps_increased
    ):
        return "bullish"
    return "neutral"


def label_from_values(
    current: dict[str, float], prior: dict[str, float]
) -> dict[str, object | None]:
    """Rule-engine labels straight from plain current/prior value dicts (any consistent unit)."""
    revenue_pct = _pct_change(current.get("revenue"), prior.get("revenue"))
    net_income_pct = _pct_change(current.get("net_income"), prior.get("net_income"))
    share_pct = _pct_change(current.get("shares_outstanding"), prior.get("shares_outstanding"))
    eps_increased = _eps_increased(current.get("eps_diluted"), prior.get("eps_diluted"))
    net_income = current.get("net_income")
    return {
        "revenue_growth": _revenue_growth(revenue_pct),
        "profitability_trend": _profitability_trend(net_income, net_income_pct),
        "ocf_covers_net_income": _ocf_covers_net_income(
            current.get("operating_cash_flow"), net_income
        ),
        "eps_increased": eps_increased,
        "leverage": _leverage(current.get("equity"), current.get("long_term_debt")),
        "liquidity": _liquidity(current.get("cash"), current.get("long_term_debt")),
        "share_count": _share_count(share_pct),
        "overall_signal": _overall_signal(net_income, revenue_pct, net_income_pct, eps_increased),
    }


def label(fs: FactSet) -> dict[str, object | None]:
    """Rule-engine labels for a :class:`isc.facts.FactSet`."""
    current = {k: v.value for k, v in fs.current.items()}
    prior = {k: v.value for k, v in fs.prior.items()}
    return label_from_values(current, prior)
