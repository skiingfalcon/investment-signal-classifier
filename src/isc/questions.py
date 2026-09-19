"""The Simple Jev question set: typed, cheap, and worded from ``rules.THRESHOLDS`` so the
prompt and the deterministic rule engine can never disagree about what a label means.

Question and criteria types mirror jev-email-cascade's ``questions.py`` (frozen dataclasses with
``to_json``), because that shape is exactly the ``ClassifierRequest`` question schema in
``common/request_schema.py``: ``Choice.criteria`` -> ``dict[str, str]``, ``Score.criteria`` ->
``list[str]``, ``Noul.criteria`` -> optional ``{"true": ..., "false": ...}``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from isc.rules import RULE_KEYS, THRESHOLDS


@dataclass(frozen=True)
class Noul:
    instructions: str
    criteria: dict[str, str] | None = None

    def to_json(self) -> dict:
        d: dict = {"type": "noul", "instructions": self.instructions}
        if self.criteria:
            d["criteria"] = self.criteria
        return d


@dataclass(frozen=True)
class Choice:
    instructions: str
    criteria: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"type": "choice", "instructions": self.instructions, "criteria": self.criteria}


@dataclass(frozen=True)
class Score:
    instructions: str
    criteria: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"type": "score", "instructions": self.instructions, "criteria": self.criteria}


Question = Noul | Choice | Score

_PREAMBLE = (
    "Use only the numbers in the state. Percent changes are given as "
    "(current - prior) / |prior| x 100, already computed for you as change_pct."
)

_T = THRESHOLDS

QUESTIONS: dict[str, Question] = {
    "revenue_growth": Choice(
        instructions=f"{_PREAMBLE} Classify the change in revenue from the prior year.",
        criteria={
            "growing": f"Revenue change is at least +{_T['revenue_pct']:.1f}% versus the prior year.",
            "flat": f"Revenue change is between -{_T['revenue_pct']:.1f}% and +{_T['revenue_pct']:.1f}%.",
            "declining": f"Revenue change is -{_T['revenue_pct']:.1f}% or lower versus the prior year.",
            "other": "Current or prior revenue is not reported in the state.",
        },
    ),
    "profitability_trend": Choice(
        instructions=f"{_PREAMBLE} Classify the trend in net income from the prior year.",
        criteria={
            "loss_making": "Current-year net income is negative.",
            "improving": f"Net income is positive and its change is at least +{_T['net_income_pct']:.1f}%.",
            "stable": f"Net income is positive and its change is between -{_T['net_income_pct']:.1f}% and +{_T['net_income_pct']:.1f}%.",
            "deteriorating": f"Net income is positive and its change is -{_T['net_income_pct']:.1f}% or lower.",
            "other": "Current or prior net income is not reported in the state.",
        },
    ),
    "ocf_covers_net_income": Noul(
        instructions=f"{_PREAMBLE} Operating cash flow (current year) is greater than or equal "
        "to net income (current year). Compare the two current-year values directly.",
        criteria={
            "true": "Current-year operating cash flow is at least current-year net income.",
            "false": "Current-year operating cash flow is less than current-year net income.",
        },
    ),
    "eps_increased": Noul(
        instructions=f"{_PREAMBLE} Diluted earnings per share this year is greater than diluted "
        "earnings per share in the prior year.",
        criteria={
            "true": "Current-year diluted EPS is greater than prior-year diluted EPS.",
            "false": "Current-year diluted EPS is less than or equal to prior-year diluted EPS.",
        },
    ),
    "leverage": Score(
        instructions=f"{_PREAMBLE} Rate leverage using the ratio of long-term debt to equity, "
        "both current year.",
        criteria=[
            f"Low: long-term debt is less than {_T['de_low']:.1f}x equity, or there is no long-term debt.",
            f"Moderate: long-term debt is between {_T['de_low']:.1f}x and {_T['de_high']:.1f}x equity.",
            f"High: long-term debt is more than {_T['de_high']:.1f}x equity, or equity is zero or negative.",
        ],
    ),
    "liquidity": Choice(
        instructions=f"{_PREAMBLE} Classify liquidity using the ratio of cash to long-term debt, "
        "both current year.",
        criteria={
            "strong": f"Cash is at least {_T['cash_to_debt_strong'] * 100:.0f}% of long-term debt, or there is no long-term debt.",
            "adequate": f"Cash is between {_T['cash_to_debt_adequate'] * 100:.0f}% and {_T['cash_to_debt_strong'] * 100:.0f}% of long-term debt.",
            "thin": f"Cash is less than {_T['cash_to_debt_adequate'] * 100:.0f}% of long-term debt.",
            "other": "Current-year cash or long-term debt is not reported in the state.",
        },
    ),
    "share_count": Choice(
        instructions=f"{_PREAMBLE} Classify the change in diluted shares outstanding from the "
        "prior year.",
        criteria={
            "buyback": f"Share count change is -{_T['share_pct']:.1f}% or lower (shares decreased).",
            "stable": f"Share count change is between -{_T['share_pct']:.1f}% and +{_T['share_pct']:.1f}%.",
            "dilution": f"Share count change is +{_T['share_pct']:.1f}% or higher (shares increased).",
            "other": "Current or prior shares outstanding is not reported in the state.",
        },
    ),
    "overall_signal": Choice(
        instructions=f"{_PREAMBLE} Judge the overall investment signal from this filing's numbers "
        "alone. Check bearish first, then bullish; anything else is neutral.",
        criteria={
            "bearish": (
                f"Net income is negative, OR net income change is -{_T['net_income_pct']:.1f}% or "
                f"lower, OR revenue change is -{_T['revenue_pct']:.1f}% or lower."
            ),
            "bullish": (
                f"Not bearish, AND revenue change is at least +{_T['revenue_pct']:.1f}%, AND net "
                f"income change is at least +{_T['net_income_pct']:.1f}%, AND diluted EPS increased "
                "versus the prior year."
            ),
            "neutral": "Not bearish and not bullish by the definitions above.",
            "other": "Revenue change, net income change, or EPS comparison is not determinable "
            "from the state.",
        },
    ),
}

assert set(QUESTIONS) == set(RULE_KEYS), "questions.py and rules.py must define the same keys"


def questions_json(questions: dict[str, Question] = QUESTIONS) -> dict:
    return {qid: q.to_json() for qid, q in questions.items()}


def questions_hash(questions: dict[str, Question] = QUESTIONS) -> str:
    payload = json.dumps(questions_json(questions), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _claim_text(qid: str, answer_value) -> str | None:
    """Render "the facts support this statement" text for a stage-1 answer."""
    q = QUESTIONS[qid]
    if isinstance(q, Choice):
        if answer_value not in q.criteria:
            return None
        return q.criteria[answer_value]
    if isinstance(q, Score):
        try:
            level = int(round(answer_value))
        except (TypeError, ValueError):
            return None
        if not 0 <= level < len(q.criteria):
            return None
        return q.criteria[level]
    return None  # Noul questions are not re-verified; they already are a probability.


def verify_questions(
    stage1_values: dict[str, object], rules_values: dict[str, object]
) -> dict[str, Noul]:
    """One ``supports_<qid>`` Noul per disputed Choice/Score question.

    A question is disputed here when the stage-1 value differs from the rule engine's, or when
    the rule engine has no opinion ("other"/None) so there is nothing to compare against. The
    claim under test is always the *stage-1* answer: a low support score is itself the signal
    that stage 1 should not be trusted, without needing a second claim for "the rules were right".
    """
    out: dict[str, Noul] = {}
    for qid, jev_value in stage1_values.items():
        if qid not in QUESTIONS or isinstance(QUESTIONS[qid], Noul):
            continue
        rules_value = rules_values.get(qid)
        if jev_value == rules_value:
            continue
        claim = _claim_text(qid, jev_value)
        if claim is None:
            continue
        out[f"supports_{qid}"] = Noul(
            instructions=f"{_PREAMBLE} The facts support this statement: {claim}",
            criteria={
                "true": "The stated numeric condition holds given the state.",
                "false": "The stated numeric condition does not hold given the state.",
            },
        )
    return out
