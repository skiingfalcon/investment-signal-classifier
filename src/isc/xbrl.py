"""Selecting values out of EDGAR XBRL ``companyfacts.json``.

Reimplements the relevant slice of llama-cpp-spark's
``src/spark_llm/evals/sec/questions.py::select_fact`` rather than depending on the ``spark_llm``
package (which pulls platform detection, lxml/bs4/tiktoken, and its own Settings for a handful of
lines of pure logic). The one deliberate difference: this selector has no accession number to
prefer (we read prior fiscal years, not just the filing being scored), so ranking drops that step
and instead prefers entries carrying a calendar ``frame`` (EDGAR's own de-duplication signal),
then the latest ``filed`` date.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class XbrlTag:
    tag: str
    key: str
    kind: str = "duration"  # duration | instant | ytd
    unit: str = "USD"
    aliases: tuple[str, ...] = ()
    accept_aliases: bool = False


# The 11 tags evaluated by llama-cpp-spark's SEC suite (evals.toml [[sec.xbrl_tags]]), with a
# short snake_case key for this project's FactSet/rule engine. `load_tags()` can cross-check this
# list against evals.toml so the two projects cannot silently drift apart.
TAGS: tuple[XbrlTag, ...] = (
    XbrlTag(
        tag="Revenues",
        key="revenue",
        kind="duration",
        aliases=(
            "RegulatedAndUnregulatedOperatingRevenue",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueNet",
        ),
        accept_aliases=True,
    ),
    XbrlTag(
        tag="NetIncomeLoss",
        key="net_income",
        kind="duration",
        aliases=("ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"),
    ),
    XbrlTag(tag="OperatingIncomeLoss", key="operating_income", kind="duration"),
    XbrlTag(tag="EarningsPerShareDiluted", key="eps_diluted", kind="duration", unit="USD/shares"),
    XbrlTag(
        tag="NetCashProvidedByUsedInOperatingActivities", key="operating_cash_flow", kind="ytd"
    ),
    XbrlTag(tag="Assets", key="total_assets", kind="instant"),
    XbrlTag(tag="Liabilities", key="total_liabilities", kind="instant"),
    XbrlTag(
        tag="StockholdersEquity",
        key="equity",
        kind="instant",
        aliases=("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",),
    ),
    XbrlTag(tag="CashAndCashEquivalentsAtCarryingValue", key="cash", kind="instant"),
    XbrlTag(
        tag="LongTermDebtNoncurrent",
        key="long_term_debt",
        kind="instant",
        aliases=("LongTermDebtAndCapitalLeaseObligations",),
        accept_aliases=True,
    ),
    XbrlTag(
        tag="CommonStockSharesOutstanding",
        key="shares_outstanding",
        kind="instant",
        unit="shares",
        aliases=("EntityCommonStockSharesOutstanding",),
    ),
)

TAG_BY_KEY: dict[str, XbrlTag] = {t.key: t for t in TAGS}


def load_tags(evals_toml: Path | None) -> tuple[XbrlTag, ...]:
    """Return TAGS, or raise if a reachable evals.toml disagrees with the vendored copy."""
    if evals_toml is None or not evals_toml.is_file():
        return TAGS
    raw = tomllib.loads(evals_toml.read_text())
    remote = {t["tag"] for t in raw.get("sec", {}).get("xbrl_tags", [])}
    local = {t.tag for t in TAGS}
    if remote and remote != local:
        raise ValueError(
            f"xbrl.TAGS is out of sync with {evals_toml}: "
            f"only here={local - remote}, only there={remote - local}"
        )
    return TAGS


def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _entries(facts: dict[str, Any], tag: XbrlTag) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    gaap = facts.get("facts", {}).get("us-gaap", {})
    dei = facts.get("facts", {}).get("dei", {})
    for concept in [tag.tag, *tag.aliases]:
        node = gaap.get(concept) or dei.get(concept)
        if not node:
            continue
        for unit, entries in node.get("units", {}).items():
            if unit != tag.unit:
                continue
            for e in entries:
                out.append({**e, "concept": concept, "unit": unit})
    return out


def _duration_ok(kind: str, form: str, e: dict[str, Any]) -> bool:
    if kind == "instant":
        return "start" not in e
    if "start" not in e:
        return False
    d = _days(e["start"], e["end"])
    if kind in ("duration", "ytd"):
        return 340 <= d <= 380 if form == "10-K" else 80 <= d <= 100
    return False


def period_candidates(
    facts: dict[str, Any], tag: XbrlTag, form: str, report_date: str
) -> list[dict[str, Any]]:
    return [
        e
        for e in _entries(facts, tag)
        if e.get("end") == report_date and _duration_ok(tag.kind, form, e)
    ]


def select_fact(
    facts: dict[str, Any], tag: XbrlTag, *, form: str = "10-K", report_date: str
) -> dict[str, Any] | None:
    """Pick the single fact for ``tag`` at ``report_date``.

    Preference: same form > any form; canonical concept, then aliases in declared order;
    entries carrying a calendar ``frame`` (EDGAR's own dedup marker); latest ``filed``.
    """
    cands = period_candidates(facts, tag, form, report_date)
    if not cands:
        return None
    pool = [e for e in cands if e.get("form") == form] or cands
    order = [tag.tag, *tag.aliases]

    def rank(e: dict[str, Any]) -> tuple:
        return (-order.index(e["concept"]), "frame" in e, e.get("filed", ""))

    return max(pool, key=rank)


def alternate_values(
    facts: dict[str, Any], tag: XbrlTag, form: str, report_date: str, chosen: dict[str, Any]
) -> list[float]:
    if not tag.accept_aliases:
        return []
    out: list[float] = []
    for e in period_candidates(facts, tag, form, report_date):
        if e["concept"] == chosen["concept"]:
            continue
        v = float(e["val"])
        if v != float(chosen["val"]) and v not in out:
            out.append(v)
    return out


def fiscal_year_ends(facts: dict[str, Any], *, form: str = "10-K") -> list[str]:
    """Distinct 10-K fiscal-year-end dates, newest first, from the Revenues/NetIncomeLoss family."""
    ends: set[str] = set()
    for key in ("revenue", "net_income"):
        tag = TAG_BY_KEY[key]
        for e in _entries(facts, tag):
            if e.get("form") == form and e.get("fp") == "FY" and _duration_ok(tag.kind, form, e):
                ends.add(e["end"])
    return sorted(ends, reverse=True)


@dataclass
class ResolvedFact:
    key: str
    value: float
    concept: str
    unit: str
    alternates: list[float] = field(default_factory=list)


def resolve_year(
    facts: dict[str, Any], report_date: str, tags: tuple[XbrlTag, ...] = TAGS, *, form: str = "10-K"
) -> dict[str, ResolvedFact]:
    """Every tag resolvable at ``report_date``, keyed by the short FactSet key."""
    out: dict[str, ResolvedFact] = {}
    for tag in tags:
        e = select_fact(facts, tag, form=form, report_date=report_date)
        if e is None:
            continue
        out[tag.key] = ResolvedFact(
            key=tag.key,
            value=float(e["val"]),
            concept=e["concept"],
            unit=e["unit"],
            alternates=alternate_values(facts, tag, form, report_date, e),
        )
    return out
