"""Routing policy: thresholds are decisions, not model output (see jev-email-cascade's own
policy.py docstring, which makes the same point). Tune these against a labelled sample.

Three-stage resolution per question:

1. **Stage 1.** Accept the JEV answer if it clears its confidence threshold and either agrees
   with the deterministic rule engine or the rule engine has no opinion (missing data ->
   ``None``/``"other"``). Otherwise the question is disputed.
2. **Stage 2** (optional). Ask one more Noul: "the facts support JEV's stage-1 claim". High
   support accepts JEV's answer; low support falls back to the rule engine's answer when it has
   one, otherwise the question stays disputed.
3. **Escalation** (optional). Remaining disputes go to a generative arbiter (``isc.verify``) with
   the full picture (state, JEV answers, rule-engine answers). Its answer becomes final. A route
   is ``escalated`` only if every disputed question got a valid arbiter answer that is not a
   three-way split (arbiter, JEV, and rules all disagree); otherwise it is ``review``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from isc.backends import Answer
from isc.questions import QUESTIONS, Choice, Noul, Question, Score

POLICY: dict[str, Any] = {
    "choice_conf": {"overall_signal": 0.70, "*": 0.60},
    "score_conf": 0.50,
    "noul_act": 0.75,  # >= act -> true, <= 1-act -> false, in between -> cannot tell
    "support_min": 0.70,  # stage-2 support needed to accept JEV's stage-1 claim
}


class Route(StrEnum):
    AUTO = "auto"
    VERIFIED = "verified"
    ESCALATED = "escalated"
    REVIEW = "review"


class QuestionOutcome(BaseModel):
    jev: Any = None
    jev_conf: float | None = None
    rules: Any = None
    agree_jev_rules: bool | None = None
    support_jev: float | None = None
    generative: Any = None
    final: Any = None
    resolved_by: str = "unresolved"  # stage1 | stage2 | generative | unresolved
    reasons: list[str] = []


class Decision(BaseModel):
    route: Route
    outcomes: dict[str, QuestionOutcome]
    final_signal: Any = None
    reasons: list[str] = []


def _choice_threshold(qid: str) -> float:
    table = POLICY["choice_conf"]
    return float(table.get(qid, table["*"]))


def _jev_value_and_conf(
    qid: str, answer: Answer | None, question: Question
) -> tuple[Any, float | None, bool]:
    """Returns (value, confidence-like, is_uncertain)."""
    if answer is None or answer.error:
        return None, None, True
    if isinstance(question, Choice):
        conf = answer.confidence
        return answer.choice, conf, conf is None or conf < _choice_threshold(qid)
    if isinstance(question, Score):
        conf = answer.confidence
        level = None if answer.score is None else int(round(answer.score))
        return level, conf, conf is None or conf < POLICY["score_conf"]
    # Noul
    p = answer.noul
    if p is None:
        return None, None, True
    act = POLICY["noul_act"]
    if p >= act:
        value: bool | None = True
    elif p <= 1 - act:
        value = False
    else:
        value = None
    return value, p, value is None


def decide_stage1(
    answers: dict[str, Answer],
    rules_values: dict[str, Any],
    questions: dict[str, Question] = QUESTIONS,
) -> tuple[dict[str, QuestionOutcome], list[str]]:
    outcomes: dict[str, QuestionOutcome] = {}
    disputed: list[str] = []
    for qid, question in questions.items():
        if isinstance(question, Noul) and qid.startswith("supports_"):
            continue  # stage-2 claim questions are scored separately, not through this table
        rules_value = rules_values.get(qid)
        answer = answers.get(qid)
        jev_value, jev_conf, uncertain = _jev_value_and_conf(qid, answer, question)
        agree = None if (jev_value is None or rules_value is None) else jev_value == rules_value
        rules_has_no_opinion = rules_value in (None, "other")

        reasons = []
        if answer is None or (answer and answer.error):
            reasons.append("backend_error")
        if uncertain:
            reasons.append("low_confidence")
        if agree is False:
            reasons.append("disagrees_with_rules")

        outcome = QuestionOutcome(
            jev=jev_value,
            jev_conf=jev_conf,
            rules=rules_value,
            agree_jev_rules=agree,
            reasons=reasons,
        )
        if not uncertain and (agree is True or rules_has_no_opinion):
            outcome.final = jev_value
            outcome.resolved_by = "stage1"
        else:
            disputed.append(qid)
        outcomes[qid] = outcome
    return outcomes, disputed


def decide_stage2(
    outcomes: dict[str, QuestionOutcome], disputed: list[str], support_answers: dict[str, Answer]
) -> list[str]:
    still_disputed: list[str] = []
    for qid in disputed:
        outcome = outcomes[qid]
        support_answer = support_answers.get(f"supports_{qid}")
        support = support_answer.noul if support_answer else None
        outcome.support_jev = support
        if support is not None and support >= POLICY["support_min"]:
            outcome.final = outcome.jev
            outcome.resolved_by = "stage2"
            outcome.reasons.append(f"stage2 supports jev ({support:.2f})")
        elif outcome.rules not in (None, "other"):
            outcome.final = outcome.rules
            outcome.resolved_by = "stage2"
            outcome.reasons.append(
                f"stage2 does not support jev ({support!r}); defaulting to rules"
            )
        else:
            still_disputed.append(qid)
    return still_disputed


def finalize(
    outcomes: dict[str, QuestionOutcome],
    still_disputed: list[str],
    generative: Any | None,
    gen_error: str | None,
) -> Decision:
    reasons: list[str] = []
    if not still_disputed:
        any_stage2 = any(o.resolved_by == "stage2" for o in outcomes.values())
        route = Route.VERIFIED if any_stage2 else Route.AUTO
    elif generative is None:
        route = Route.REVIEW
        reasons.append(gen_error or "no arbiter available")
        for qid in still_disputed:
            outcomes[qid].resolved_by = "unresolved"
    else:
        all_resolved = True
        for qid in still_disputed:
            outcome = outcomes[qid]
            gen_value = getattr(generative, qid, None)
            outcome.generative = gen_value
            if gen_value is None:
                all_resolved = False
                continue
            agree_jev = gen_value == outcome.jev
            agree_rules = gen_value == outcome.rules
            outcome.reasons.append(f"generative agree_jev={agree_jev} agree_rules={agree_rules}")
            three_way_split = (
                not agree_jev
                and not agree_rules
                and outcome.jev is not None
                and outcome.rules not in (None, "other")
            )
            if three_way_split:
                all_resolved = False
            outcome.final = gen_value
            outcome.resolved_by = "generative"
        route = Route.ESCALATED if all_resolved else Route.REVIEW

    final_signal = outcomes["overall_signal"].final if "overall_signal" in outcomes else None
    return Decision(route=route, outcomes=outcomes, final_signal=final_signal, reasons=reasons)
