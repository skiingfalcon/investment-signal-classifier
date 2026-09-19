"""Render a FactSet into the ``state`` object sent to Simple Jev.

Default mode is ``derived``: values in human-scaled units, percent changes and ratios
precomputed, missing facts listed explicitly. Simple Jev reads a single next-token
distribution after one prefill; there is no scratchpad for multi-digit arithmetic, so the rule
engine owns arithmetic and the classifier owns the threshold judgment. ``raw`` mode (values only,
no derived fields) exists to measure that gap, not as an alternative default.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from isc.facts import FactSet

_USD_MILLIONS = {
    "revenue",
    "net_income",
    "operating_income",
    "operating_cash_flow",
    "total_assets",
    "total_liabilities",
    "equity",
    "cash",
    "long_term_debt",
}
_SHARES_MILLIONS = {"shares_outstanding"}
_PER_SHARE = {"eps_diluted"}

UNITS_NOTE = (
    "USD millions unless noted; eps_diluted in USD per share; shares_outstanding in millions; "
    "change_pct = (current - prior) / |prior| x 100"
)


def _scaled(key: str, value: float) -> float:
    if key in _USD_MILLIONS or key in _SHARES_MILLIONS:
        return round(value / 1_000_000.0, 1)
    if key in _PER_SHARE:
        return round(value, 2)
    return round(value, 2)


def _year_block(fs: FactSet, which: Literal["current", "prior"]) -> dict[str, float]:
    values = fs.current if which == "current" else fs.prior
    return {key: _scaled(key, fv.value) for key, fv in values.items()}


def _change_pct(fs: FactSet) -> dict[str, float]:
    out = {}
    for key, cur in fs.current.items():
        prior = fs.prior.get(key)
        if prior is None or prior.value == 0:
            continue
        out[key] = round((cur.value - prior.value) / abs(prior.value) * 100.0, 1)
    return out


def _ratios_block(fs: FactSet) -> dict[str, float]:
    r = fs.ratios
    out = {}
    if r.net_margin is not None:
        out["net_margin_pct"] = round(r.net_margin * 100.0, 1)
    if r.operating_margin is not None:
        out["operating_margin_pct"] = round(r.operating_margin * 100.0, 1)
    if r.ocf_to_net_income is not None:
        out["ocf_to_net_income"] = round(r.ocf_to_net_income, 2)
    if r.debt_to_equity is not None:
        out["debt_to_equity"] = round(r.debt_to_equity, 2)
    if r.cash_to_debt is not None:
        out["cash_to_debt"] = round(r.cash_to_debt, 2)
    if r.liabilities_to_assets is not None:
        out["liabilities_to_assets"] = round(r.liabilities_to_assets, 2)
    return out


def _not_reported(fs: FactSet) -> list[str]:
    out = [f"current.{k}" for k in fs.quality.missing_current]
    out += [f"prior.{k}" for k in fs.quality.missing_prior]
    return sorted(out)


def render(fs: FactSet, mode: Literal["derived", "raw"] = "derived") -> dict:
    state: dict = {
        "company": fs.company or fs.ticker,
        "form": fs.form,
        "fiscal_year_end": fs.fiscal_year_end,
        "prior_year_end": fs.prior_year_end,
        "units": UNITS_NOTE,
        "current": _year_block(fs, "current"),
        "prior": _year_block(fs, "prior"),
        "not_reported": _not_reported(fs),
    }
    if mode == "derived":
        state["change_pct"] = _change_pct(fs)
        state["ratios"] = _ratios_block(fs)
    return state


def state_hash(state: dict) -> str:
    payload = json.dumps(state, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:12]
