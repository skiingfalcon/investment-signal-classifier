"""FactSet: one company-year's financial facts (current + prior), plus derived ratios.

Two sources populate the same shape:

- ``xbrl_factsets``: both years read straight from EDGAR XBRL company facts. Exact ground truth.
- ``model_factsets``: the *current* year comes from a committed llama-cpp-spark extraction run
  (``state/evals/sec/<model>/<ts>-extract-full/results.jsonl``), carrying whatever extraction
  errors that model made; the *prior* year still comes from XBRL, since the extraction task only
  covers the filing's own fiscal year. This is what makes the "extraction impact" analysis
  possible: identical questions, one source with real upstream errors, one without.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from isc import xbrl

Key = str  # one of xbrl.TAG_BY_KEY


class FactValue(BaseModel):
    value: float
    source: Literal["xbrl", "model"]
    concept: str | None = None
    run: str | None = None
    correct: bool | None = None
    off_by_scale: bool = False
    expected: float | None = None


class Ratios(BaseModel):
    revenue_yoy: float | None = None
    net_income_yoy: float | None = None
    eps_yoy: float | None = None
    operating_cash_flow_yoy: float | None = None
    share_count_change: float | None = None
    net_margin: float | None = None
    operating_margin: float | None = None
    ocf_to_net_income: float | None = None
    debt_to_equity: float | None = None
    cash_to_debt: float | None = None
    liabilities_to_assets: float | None = None


class DataQuality(BaseModel):
    missing_current: list[str] = []
    missing_prior: list[str] = []
    model_wrong: list[str] = []
    off_by_scale: list[str] = []
    negative_equity: bool = False
    no_long_term_debt: bool = False


class FactSet(BaseModel):
    id: str
    ticker: str
    company: str | None = None
    form: Literal["10-K"] = "10-K"
    fiscal_year_end: str
    prior_year_end: str | None
    source: str  # "xbrl" | "model:<run>"
    current: dict[Key, FactValue]
    prior: dict[Key, FactValue]
    ratios: Ratios
    quality: DataQuality


def _yoy(cur: float | None, prior: float | None) -> float | None:
    if cur is None or prior is None or prior == 0:
        return None
    return (cur - prior) / abs(prior)


def derive(current: dict[str, float], prior: dict[str, float]) -> tuple[Ratios, DataQuality]:
    quality = DataQuality()
    revenue, net_income = current.get("revenue"), current.get("net_income")
    equity, ltd, cash = current.get("equity"), current.get("long_term_debt"), current.get("cash")
    ocf = current.get("operating_cash_flow")
    assets, liab = current.get("total_assets"), current.get("total_liabilities")

    operating_income = current.get("operating_income")
    net_margin = (
        net_income / revenue if (net_income is not None and revenue not in (None, 0)) else None
    )
    operating_margin = (
        operating_income / revenue
        if (operating_income is not None and revenue not in (None, 0))
        else None
    )
    ocf_to_net_income = (
        ocf / net_income if (ocf is not None and net_income not in (None, 0)) else None
    )

    if equity is not None and equity <= 0:
        quality.negative_equity = True
        debt_to_equity = None
    else:
        debt_to_equity = ltd / equity if (ltd is not None and equity not in (None, 0)) else None

    if ltd is not None and ltd == 0:
        quality.no_long_term_debt = True
        cash_to_debt = None
    else:
        cash_to_debt = cash / ltd if (cash is not None and ltd not in (None, 0)) else None

    liabilities_to_assets = (
        liab / assets if (liab is not None and assets not in (None, 0)) else None
    )

    ratios = Ratios(
        revenue_yoy=_yoy(revenue, prior.get("revenue")),
        net_income_yoy=_yoy(net_income, prior.get("net_income")),
        eps_yoy=_yoy(current.get("eps_diluted"), prior.get("eps_diluted")),
        operating_cash_flow_yoy=_yoy(ocf, prior.get("operating_cash_flow")),
        share_count_change=_yoy(current.get("shares_outstanding"), prior.get("shares_outstanding")),
        net_margin=net_margin,
        operating_margin=operating_margin,
        ocf_to_net_income=ocf_to_net_income,
        debt_to_equity=debt_to_equity,
        cash_to_debt=cash_to_debt,
        liabilities_to_assets=liabilities_to_assets,
    )
    return ratios, quality


def load_companyfacts(sec_data_dir: Path, ticker: str) -> dict:
    path = sec_data_dir / ticker / "companyfacts.json"
    return json.loads(path.read_text())


def _xbrl_year_values(
    facts: dict, report_date: str
) -> tuple[dict[str, float], dict[str, FactValue]]:
    resolved = xbrl.resolve_year(facts, report_date)
    plain = {k: r.value for k, r in resolved.items()}
    typed = {
        k: FactValue(value=r.value, source="xbrl", concept=r.concept) for k, r in resolved.items()
    }
    return plain, typed


def xbrl_factset(
    facts: dict, ticker: str, fy_end: str, prior_end: str | None, *, company: str | None = None
) -> FactSet:
    cur_plain, cur_typed = _xbrl_year_values(facts, fy_end)
    prior_plain, prior_typed = (
        ({}, {}) if prior_end is None else _xbrl_year_values(facts, prior_end)
    )
    ratios, quality = derive(cur_plain, prior_plain)
    quality.missing_current = sorted(set(xbrl.TAG_BY_KEY) - set(cur_typed))
    quality.missing_prior = (
        sorted(set(xbrl.TAG_BY_KEY) - set(prior_typed)) if prior_end else list(xbrl.TAG_BY_KEY)
    )
    return FactSet(
        id=f"{ticker}:FY{fy_end}:xbrl",
        ticker=ticker,
        company=company,
        fiscal_year_end=fy_end,
        prior_year_end=prior_end,
        source="xbrl",
        current=cur_typed,
        prior=prior_typed,
        ratios=ratios,
        quality=quality,
    )


def xbrl_twin(fs: FactSet, sec_data_dir: Path) -> FactSet:
    """The pure-XBRL FactSet for the same ticker/fiscal year as ``fs``.

    For an ``xbrl``-source FactSet this is ``fs`` itself. For a ``model:*``-source FactSet it is
    the ground truth the extraction was scored against -- comparing ``rules.label(fs)`` against
    ``rules.label(xbrl_twin(fs, ...))`` measures how often an upstream extraction error changed
    the final label, independent of whether the double check caught it.
    """
    if fs.source == "xbrl":
        return fs
    facts = load_companyfacts(sec_data_dir, fs.ticker)
    return xbrl_factset(facts, fs.ticker, fs.fiscal_year_end, fs.prior_year_end, company=fs.company)


def xbrl_factsets(
    facts: dict, ticker: str, *, years: int = 5, company: str | None = None
) -> list[FactSet]:
    ends = xbrl.fiscal_year_ends(facts)
    out = []
    for i, fy_end in enumerate(ends[:years]):
        prior_end = ends[i + 1] if i + 1 < len(ends) else None
        out.append(xbrl_factset(facts, ticker, fy_end, prior_end, company=company))
    return out


def model_factsets(
    results_jsonl: Path, sec_data_dir: Path, *, run_name: str | None = None
) -> list[FactSet]:
    """One FactSet per (ticker, report_date) row group in a committed extraction run.

    Current-year values come from the run's ``parsed`` column (with ``correct``/``off_by_scale``/
    ``expected`` passed through); ``parsed: null`` rows are recorded as missing rather than
    dropped. The prior year is read from XBRL, since extraction only covers the filing's own
    fiscal year.
    """
    run_name = run_name or results_jsonl.parent.name
    rows: dict[tuple[str, str], list[dict]] = {}
    for line in results_jsonl.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("form") != "10-K":
            continue
        rows.setdefault((row["ticker"], row["report_date"]), []).append(row)

    out: list[FactSet] = []
    facts_cache: dict[str, dict] = {}
    tag_to_key = {t.tag: t.key for t in xbrl.TAGS}
    for (ticker, report_date), group in rows.items():
        facts = facts_cache.setdefault(ticker, load_companyfacts(sec_data_dir, ticker))
        cur_plain: dict[str, float] = {}
        cur_typed: dict[str, FactValue] = {}
        missing_current: list[str] = []
        model_wrong: list[str] = []
        off_by_scale: list[str] = []
        for row in group:
            key = tag_to_key.get(row["tag"])
            if key is None:
                continue
            parsed = row.get("parsed")
            if parsed is None:
                missing_current.append(key)
                continue
            cur_plain[key] = float(parsed)
            cur_typed[key] = FactValue(
                value=float(parsed),
                source="model",
                run=run_name,
                correct=row.get("correct"),
                off_by_scale=bool(row.get("off_by_scale", False)),
                expected=row.get("expected"),
            )
            if row.get("correct") is False:
                model_wrong.append(key)
            if row.get("off_by_scale"):
                off_by_scale.append(key)

        ends = xbrl.fiscal_year_ends(facts)
        prior_end = next((e for e in ends if e < report_date), None)
        prior_plain, prior_typed = (
            ({}, {}) if prior_end is None else _xbrl_year_values(facts, prior_end)
        )

        ratios, quality = derive(cur_plain, prior_plain)
        quality.missing_current = sorted(set(missing_current))
        quality.missing_prior = (
            sorted(set(xbrl.TAG_BY_KEY) - set(prior_typed)) if prior_end else list(xbrl.TAG_BY_KEY)
        )
        quality.model_wrong = sorted(set(model_wrong))
        quality.off_by_scale = sorted(set(off_by_scale))

        out.append(
            FactSet(
                id=f"{ticker}:FY{report_date}:model:{run_name}",
                ticker=ticker,
                fiscal_year_end=report_date,
                prior_year_end=prior_end,
                source=f"model:{run_name}",
                current=cur_typed,
                prior=prior_typed,
                ratios=ratios,
                quality=quality,
            )
        )
    return out


def write_facts(path: Path, factsets: list[FactSet]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for fs in factsets:
            f.write(fs.model_dump_json())
            f.write("\n")


def read_facts(path: Path) -> list[FactSet]:
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            out.append(FactSet.model_validate_json(line))
    return out
