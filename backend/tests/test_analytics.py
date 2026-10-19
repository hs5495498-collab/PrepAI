import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import analytics


def ev(category, total, relevance=25, correctness=30, completeness=20, clarity=8, when="2026-01-01T00:00:00+00:00"):
    return {
        "category": category, "total_score": total,
        "relevance_score": relevance, "correctness_score": correctness,
        "completeness_score": completeness, "clarity_score": clarity,
        "evaluated_at": when,
    }


# ---------- Empty history ----------

def test_no_interviews_at_all():
    summary = analytics.build_summary(0, 0, [])
    assert summary["total_interviews"] == 0
    assert summary["completion_rate"] is None
    assert summary["average_score"] is None
    assert summary["highest_score"] is None
    assert summary["progress"] == []
    assert summary["progress_sufficient"] is False


def test_interviews_but_no_evaluations_not_treated_as_zero():
    summary = analytics.build_summary(5, 3, [])
    assert summary["completed_interviews"] == 3
    assert summary["average_score"] is None  # never 0, which would look like poor performance
    assert summary["by_category"] == {}
    assert summary["by_dimension"] == {}


# ---------- Definitions: completion rate, averages ----------

def test_completion_rate_uses_total_interviews_as_denominator():
    summary = analytics.build_summary(4, 3, [])
    assert summary["completion_rate"] == round(3 / 4, 3)


def test_average_score_is_mean_across_evaluated_answers_not_interviews():
    # Two answers from one interview, one from another - average must be
    # the mean of all three individual answers, not an average of
    # per-interview averages (which would weight them differently).
    evaluations = [ev("technical", 90), ev("technical", 90), ev("hr", 30)]
    summary = analytics.build_summary(2, 2, evaluations)
    assert summary["average_score"] == round((90 + 90 + 30) / 3, 1)


def test_highest_and_most_recent_score():
    evaluations = [
        ev("technical", 50, when="2026-01-01T00:00:00+00:00"),
        ev("technical", 95, when="2026-01-02T00:00:00+00:00"),
        ev("technical", 70, when="2026-01-03T00:00:00+00:00"),
    ]
    summary = analytics.build_summary(1, 1, evaluations)
    assert summary["highest_score"] == 95
    assert summary["most_recent_score"] == 70  # latest by evaluated_at, not highest


# ---------- Category and dimension breakdowns ----------

def test_category_breakdown_only_includes_attempted_categories():
    evaluations = [ev("technical", 80), ev("technical", 60)]
    summary = analytics.build_summary(1, 1, evaluations)
    assert set(summary["by_category"].keys()) == {"technical"}
    assert summary["by_category"]["technical"]["count"] == 2
    assert summary["by_category"]["technical"]["average_score"] == 70.0


def test_dimension_breakdown_present_for_all_four_dimensions():
    evaluations = [ev("technical", 70, relevance=20, correctness=25, completeness=15, clarity=6)]
    summary = analytics.build_summary(1, 1, evaluations)
    assert set(summary["by_dimension"].keys()) == {
        "relevance_score", "correctness_score", "completeness_score", "clarity_score"
    }
    assert summary["by_dimension"]["relevance_score"]["average"] == 20.0
    assert summary["by_dimension"]["relevance_score"]["max"] == 30


def test_strongest_and_weakest_dimension_require_minimum_samples():
    # Only 1 evaluation - must not claim a confident strongest/weakest.
    evaluations = [ev("technical", 70, relevance=5, correctness=30, completeness=20, clarity=10)]
    summary = analytics.build_summary(1, 1, evaluations)
    assert summary["strongest_dimension"] is None
    assert summary["weakest_dimension"] is None


def test_strongest_and_weakest_dimension_with_enough_samples():
    evaluations = [
        ev("technical", 70, relevance=5, correctness=35, completeness=20, clarity=8),
        ev("technical", 70, relevance=4, correctness=35, completeness=20, clarity=8),
        ev("technical", 70, relevance=6, correctness=35, completeness=20, clarity=8),
    ]
    summary = analytics.build_summary(1, 1, evaluations)
    assert summary["strongest_dimension"] == "correctness_score"  # 35/35 = 100%
    assert summary["weakest_dimension"] == "relevance_score"  # ~5/30 = 17%


# ---------- Progress / determinism ----------

def test_progress_sufficient_requires_at_least_two_points():
    summary_one = analytics.build_summary(1, 1, [ev("technical", 80)])
    assert summary_one["progress_sufficient"] is False
    summary_two = analytics.build_summary(1, 1, [ev("technical", 80), ev("technical", 85, when="2026-01-02T00:00:00+00:00")])
    assert summary_two["progress_sufficient"] is True


def test_progress_points_are_chronologically_ordered_regardless_of_input_order():
    evaluations = [
        ev("technical", 90, when="2026-01-03T00:00:00+00:00"),
        ev("technical", 50, when="2026-01-01T00:00:00+00:00"),
        ev("technical", 70, when="2026-01-02T00:00:00+00:00"),
    ]
    summary = analytics.build_summary(1, 1, evaluations)
    assert [p["score"] for p in summary["progress"]] == [50, 70, 90]


def test_results_deterministic_regardless_of_input_order():
    evaluations = [ev("technical", 80), ev("hr", 40), ev("behavioral", 60)]
    shuffled = [evaluations[2], evaluations[0], evaluations[1]]
    summary_a = analytics.build_summary(3, 3, evaluations)
    summary_b = analytics.build_summary(3, 3, shuffled)
    assert summary_a["by_category"] == summary_b["by_category"]
    assert summary_a["average_score"] == summary_b["average_score"]


def test_evaluated_answers_count_matches_input_length():
    evaluations = [ev("technical", 80), ev("technical", 60), ev("hr", 70)]
    summary = analytics.build_summary(2, 2, evaluations)
    assert summary["evaluated_answers"] == 3
