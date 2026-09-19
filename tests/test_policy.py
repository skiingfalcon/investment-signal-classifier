from types import SimpleNamespace

from isc.backends import Answer
from isc.policy import Route, decide_stage1, decide_stage2, finalize
from isc.questions import QUESTIONS

ALL_QIDS = list(QUESTIONS)


def _confident_choice(value: str) -> Answer:
    return Answer(type="choice", choice=value, confidence=0.95, probabilities={value: 0.95})


def _confident_noul(value: bool) -> Answer:
    return Answer(type="noul", noul=0.95 if value else 0.05)


def _all_agree_answers(rules_values: dict) -> dict[str, Answer]:
    answers = {}
    for qid, q in QUESTIONS.items():
        value = rules_values[qid]
        if q.__class__.__name__ == "Noul":
            answers[qid] = (
                _confident_noul(bool(value)) if value is not None else Answer(type="noul", noul=0.5)
            )
        elif q.__class__.__name__ == "Score":
            level = value if isinstance(value, int) else 0
            answers[qid] = Answer(type="score", score=float(level), confidence=0.95)
        else:
            answers[qid] = _confident_choice(value if value is not None else "other")
    return answers


BASE_RULES = {
    "revenue_growth": "growing",
    "profitability_trend": "improving",
    "ocf_covers_net_income": True,
    "eps_increased": True,
    "leverage": 0,
    "liquidity": "strong",
    "share_count": "stable",
    "overall_signal": "bullish",
}


def test_route_auto_when_everything_agrees_confidently():
    answers = _all_agree_answers(BASE_RULES)
    outcomes, disputed = decide_stage1(answers, BASE_RULES)
    assert disputed == []
    decision = finalize(outcomes, disputed, None, None)
    assert decision.route == Route.AUTO
    assert decision.final_signal == "bullish"


def test_route_verified_when_stage2_resolves_a_low_confidence_disagreement():
    answers = _all_agree_answers(BASE_RULES)
    answers["revenue_growth"] = Answer(
        type="choice", choice="flat", confidence=0.5, probabilities={"flat": 0.5, "growing": 0.5}
    )
    outcomes, disputed = decide_stage1(answers, BASE_RULES)
    assert disputed == ["revenue_growth"]
    support_answers = {"supports_revenue_growth": Answer(type="noul", noul=0.9)}
    still_disputed = decide_stage2(outcomes, disputed, support_answers)
    assert still_disputed == []
    decision = finalize(outcomes, still_disputed, None, None)
    assert decision.route == Route.VERIFIED
    assert outcomes["revenue_growth"].final == "flat"  # stage 2 backed JEV's claim
    assert outcomes["revenue_growth"].resolved_by == "stage2"


def test_stage2_falls_back_to_rules_when_support_is_low():
    answers = _all_agree_answers(BASE_RULES)
    answers["revenue_growth"] = Answer(
        type="choice", choice="flat", confidence=0.5, probabilities={"flat": 0.5, "growing": 0.5}
    )
    outcomes, disputed = decide_stage1(answers, BASE_RULES)
    support_answers = {"supports_revenue_growth": Answer(type="noul", noul=0.1)}
    still_disputed = decide_stage2(outcomes, disputed, support_answers)
    assert still_disputed == []
    assert outcomes["revenue_growth"].final == "growing"  # fell back to the rule engine
    assert outcomes["revenue_growth"].resolved_by == "stage2"


def test_route_escalated_when_generative_resolves_remaining_disputes():
    answers = _all_agree_answers(BASE_RULES)
    answers["leverage"] = Answer(type="score", score=2.0, confidence=0.3)
    rules_with_no_opinion = dict(BASE_RULES, leverage=None)  # rules can't tell either
    outcomes, disputed = decide_stage1(answers, rules_with_no_opinion)
    assert disputed == ["leverage"]
    still_disputed = decide_stage2(outcomes, disputed, {})  # no stage-2 answer available
    assert still_disputed == ["leverage"]
    generative = SimpleNamespace(leverage=1)
    decision = finalize(outcomes, still_disputed, generative, None)
    assert decision.route == Route.ESCALATED
    assert outcomes["leverage"].final == 1
    assert outcomes["leverage"].resolved_by == "generative"


def test_route_review_when_no_arbiter_is_available():
    answers = _all_agree_answers(BASE_RULES)
    answers["leverage"] = Answer(type="score", score=2.0, confidence=0.3)
    rules_with_no_opinion = dict(BASE_RULES, leverage=None)
    outcomes, disputed = decide_stage1(answers, rules_with_no_opinion)
    still_disputed = decide_stage2(outcomes, disputed, {})
    decision = finalize(outcomes, still_disputed, None, "no arbiter configured")
    assert decision.route == Route.REVIEW
    assert outcomes["leverage"].resolved_by == "unresolved"


def test_route_review_on_a_three_way_split():
    # verify=False path: stage-1 disputes go straight to the arbiter, so a rules opinion can
    # still be on the table when the arbiter disagrees with both sides.
    answers = _all_agree_answers(BASE_RULES)
    answers["liquidity"] = Answer(
        type="choice", choice="adequate", confidence=0.3, probabilities={"adequate": 0.3}
    )
    rules_disagreeing = dict(BASE_RULES, liquidity="thin")
    outcomes, disputed = decide_stage1(answers, rules_disagreeing)
    assert disputed == ["liquidity"]
    generative = SimpleNamespace(liquidity="strong")  # neither jev's "adequate" nor rules' "thin"
    decision = finalize(outcomes, disputed, generative, None)
    assert decision.route == Route.REVIEW
    assert outcomes["liquidity"].final == "strong"  # recorded even though the route is review
