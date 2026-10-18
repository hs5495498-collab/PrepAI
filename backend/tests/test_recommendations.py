import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import recommendations


def ev(category, difficulty, total, relevance=25, correctness=30, completeness=20, clarity=8, when="2026-01-01T00:00:00+00:00"):
    return {
        "category": category, "difficulty": difficulty, "total_score": total,
        "relevance_score": relevance, "correctness_score": correctness,
        "completeness_score": completeness, "clarity_score": clarity,
        "evaluated_at": when,
    }


def by_key(recs):
    return {r["key"] for r in recs}


# ---------- No history / no evaluations ----------

def test_no_history_produces_generic_beginner_recommendation():
    recs = recommendations.build_recommendations(0, [])
    assert len(recs) == 1
    assert recs[0]["key"] == "start_first_interview"
    assert recs[0]["evidence_level"] == "generic"
    assert recs[0]["evidence"] == []


def test_interviews_but_no_evaluations_produces_distinct_generic_recommendation():
    recs = recommendations.build_recommendations(2, [])
    assert len(recs) == 1
    assert recs[0]["key"] == "evaluate_an_answer"
    assert recs[0]["evidence_level"] == "generic"
    assert "2 interviews" in recs[0]["explanation"]


# ---------- Weak category performance ----------

def test_weak_category_with_sufficient_samples_is_high_priority_and_data_backed():
    evaluations = [ev("technical", "medium", 40), ev("technical", "medium", 45), ev("technical", "medium", 50)]
    recs = recommendations.build_recommendations(3, evaluations)
    weak = [r for r in recs if r["key"] == "weak_category_technical"][0]
    assert weak["priority"] == "high"
    assert weak["evidence_level"] == "data"
    assert weak["category"] == "technical"
    assert "45" in weak["reason"]  # average of 40,45,50 = 45


def test_weak_category_with_limited_samples_is_marked_limited_not_high_priority():
    evaluations = [ev("hr", "easy", 30)]
    recs = recommendations.build_recommendations(1, evaluations)
    weak = [r for r in recs if r["key"] == "weak_category_hr"][0]
    assert weak["evidence_level"] == "limited"
    assert weak["priority"] == "medium"


def test_category_never_mentioned_unless_it_has_evaluations():
    evaluations = [ev("technical", "medium", 30), ev("technical", "medium", 35), ev("technical", "medium", 32)]
    recs = recommendations.build_recommendations(3, evaluations)
    keys = by_key(recs)
    assert not any("hr" in k or "behavioral" in k for k in keys)


# ---------- Strong performance -> harder difficulty ----------

def test_strong_category_suggests_next_difficulty_up():
    evaluations = [ev("technical", "easy", 90), ev("technical", "easy", 88), ev("technical", "easy", 92)]
    recs = recommendations.build_recommendations(3, evaluations)
    strong = [r for r in recs if r["key"] == "increase_difficulty_technical"]
    assert len(strong) == 1
    assert strong[0]["difficulty"] == "medium"
    assert strong[0]["priority"] == "low"
    assert strong[0]["evidence_level"] == "data"


def test_strong_at_hard_difficulty_has_no_next_level_to_suggest():
    evaluations = [ev("technical", "hard", 95), ev("technical", "hard", 92), ev("technical", "hard", 97)]
    recs = recommendations.build_recommendations(3, evaluations)
    assert not any(r["key"] == "increase_difficulty_technical" for r in recs)


def test_single_strong_answer_does_not_trigger_difficulty_increase():
    # Avoid strong claims from a single question - must not fire with < MIN_SAMPLES_FOR_TREND.
    evaluations = [ev("technical", "easy", 95)]
    recs = recommendations.build_recommendations(1, evaluations)
    assert not any(r["key"].startswith("increase_difficulty") for r in recs)


def test_weak_and_strong_recommendations_never_contradict_for_same_category():
    evaluations = [ev("technical", "medium", 40), ev("technical", "medium", 38), ev("technical", "medium", 42)]
    recs = recommendations.build_recommendations(3, evaluations)
    keys = by_key(recs)
    assert "weak_category_technical" in keys
    assert "increase_difficulty_technical" not in keys


# ---------- Inconsistency ----------

def test_inconsistent_category_results_flagged():
    evaluations = [ev("behavioral", "medium", 20), ev("behavioral", "medium", 85), ev("behavioral", "medium", 25)]
    recs = recommendations.build_recommendations(3, evaluations)
    inconsistent = [r for r in recs if r["key"] == "inconsistent_behavioral"]
    assert len(inconsistent) == 1
    assert "20" in inconsistent[0]["reason"] and "85" in inconsistent[0]["reason"]


def test_consistent_scores_are_not_flagged_as_inconsistent():
    evaluations = [ev("behavioral", "medium", 70), ev("behavioral", "medium", 72), ev("behavioral", "medium", 68)]
    recs = recommendations.build_recommendations(3, evaluations)
    assert not any(r["key"] == "inconsistent_behavioral" for r in recs)


# ---------- Dimension weaknesses ----------

def test_weak_dimension_detected_across_categories():
    evaluations = [
        ev("technical", "medium", 70, correctness=10),
        ev("hr", "medium", 70, correctness=12),
        ev("behavioral", "medium", 70, correctness=8),
    ]
    recs = recommendations.build_recommendations(3, evaluations)
    assert any(r["key"] == "weak_dimension_correctness_score" for r in recs)


def test_missing_evaluations_are_not_treated_as_zero():
    # Only one real evaluation exists for "hr" - its average must be exactly
    # that one real score, never diluted by assumed/missing zeros.
    evaluations = [ev("hr", "medium", 80)]
    recs = recommendations.build_recommendations(1, evaluations)
    # A single strong 80 is above WEAK_SCORE_THRESHOLD, so no weak-category
    # recommendation should appear for hr at all - if missing data were
    # treated as zero, the average would drop and incorrectly flag it.
    assert not any(r["key"] == "weak_category_hr" for r in recs)


# ---------- Ordering, limits, determinism ----------

def test_recommendation_count_is_limited():
    evaluations = []
    for cat in ["technical", "hr", "behavioral"]:
        for _ in range(4):
            evaluations.append(ev(cat, "medium", 30, relevance=5, correctness=5, completeness=5, clarity=1))
    recs = recommendations.build_recommendations(4, evaluations)
    assert len(recs) <= recommendations.MAX_RECOMMENDATIONS


def test_ordering_is_deterministic_regardless_of_input_order():
    evaluations = [ev("technical", "medium", 30), ev("hr", "medium", 35), ev("technical", "medium", 32)]
    shuffled = [evaluations[2], evaluations[0], evaluations[1]]
    recs_a = recommendations.build_recommendations(3, evaluations)
    recs_b = recommendations.build_recommendations(3, shuffled)
    assert [r["key"] for r in recs_a] == [r["key"] for r in recs_b]


def test_priority_order_high_before_medium_before_low():
    evaluations = [
        ev("technical", "medium", 30), ev("technical", "medium", 32), ev("technical", "medium", 28),  # high: weak category
        ev("hr", "easy", 90), ev("hr", "easy", 92), ev("hr", "easy", 95),  # low: increase difficulty
    ]
    recs = recommendations.build_recommendations(6, evaluations)
    ranks = [recommendations.PRIORITY_RANK[r["priority"]] for r in recs]
    assert ranks == sorted(ranks)


def test_no_evaluations_list_produces_no_candidates_beyond_generic():
    recs = recommendations.build_recommendations(5, [])
    assert len(recs) == 1
    assert recs[0]["evidence_level"] == "generic"
