from isc._common import ClassifierRequest
from isc.questions import QUESTIONS, Choice, Noul, questions_hash, questions_json, verify_questions
from isc.rules import RULE_KEYS, THRESHOLDS


def test_question_ids_match_rule_keys():
    assert set(QUESTIONS) == set(RULE_KEYS)


def test_every_choice_has_an_escape_option():
    for qid, q in QUESTIONS.items():
        if isinstance(q, Choice):
            assert "other" in q.criteria, f"{qid} is missing an 'other' escape option"


def test_criteria_text_uses_the_threshold_constants():
    revenue_growth = QUESTIONS["revenue_growth"]
    assert f"{THRESHOLDS['revenue_pct']:.1f}%" in revenue_growth.criteria["growing"]
    leverage = QUESTIONS["leverage"]
    assert f"{THRESHOLDS['de_low']:.1f}x" in leverage.criteria[0]
    assert f"{THRESHOLDS['de_high']:.1f}x" in leverage.criteria[1]


def test_questions_hash_is_stable():
    assert questions_hash() == questions_hash()
    assert len(questions_hash()) == 12


def test_request_validates_through_common_schema():
    request = {
        "model": "qwen3.8-27b",
        "state": {"company": "ACME", "current": {"revenue": 100.0}},
        "questions": questions_json(),
    }
    validated = ClassifierRequest.model_validate(request)
    assert set(validated.questions) == set(QUESTIONS)


def test_verify_questions_only_covers_disputed_choice_and_score_questions():
    stage1 = {
        "revenue_growth": "growing",  # agrees with rules
        "profitability_trend": "improving",  # disagrees with rules
        "ocf_covers_net_income": True,  # Noul: never re-verified
    }
    rules_values = {
        "revenue_growth": "growing",
        "profitability_trend": "deteriorating",
        "ocf_covers_net_income": True,
    }
    verify_qs = verify_questions(stage1, rules_values)
    assert set(verify_qs) == {"supports_profitability_trend"}
    q = verify_qs["supports_profitability_trend"]
    assert isinstance(q, Noul)
    assert QUESTIONS["profitability_trend"].criteria["improving"] in q.instructions


def test_verify_questions_covers_a_question_the_rules_have_no_opinion_on():
    stage1 = {"revenue_growth": "growing"}
    rules_values = {"revenue_growth": "other"}
    verify_qs = verify_questions(stage1, rules_values)
    assert set(verify_qs) == {"supports_revenue_growth"}
