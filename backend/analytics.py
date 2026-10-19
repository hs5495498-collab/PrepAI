"""Pure, deterministic analytics calculations (Phase 10).

Like recommendations.py, this module makes no database or network calls -
it takes already-fetched, already-ownership-filtered data in (from
storage.get_user_recommendation_data) and returns a summary dict out.
Reuses recommendations.py's constants (DIMENSION_INFO, MIN_SAMPLES_FOR_TREND)
instead of duplicating them, so the two features can never silently drift
apart on what counts as "enough evidence."

Definitions (so every number has one unambiguous meaning):
- average_score: the mean of total_score across every EVALUATED ANSWER the
  account has, not an average of per-interview averages. An interview with
  more evaluated questions therefore contributes proportionally more -
  this is the simplest, least surprising definition, and matches what
  "average score across your evaluated answers" plainly means.
- completion_rate: completed_interviews / total_interviews (every interview
  the account has, completed or not). None when total_interviews is 0 -
  never displayed as 0%, which would misleadingly suggest poor performance
  rather than "no data yet."
- highest_score / most_recent_score: both drawn only from evaluated
  answers (most_recent by evaluated_at, not by interview creation date).
"""
from statistics import mean

import recommendations

DIMENSION_FIELDS = ["relevance_score", "correctness_score", "completeness_score", "clarity_score"]


def _empty_summary(total_interviews: int, completed_interviews: int) -> dict:
    return {
        "total_interviews": total_interviews,
        "completed_interviews": completed_interviews,
        "evaluated_answers": 0,
        "completion_rate": round(completed_interviews / total_interviews, 3) if total_interviews else None,
        "average_score": None,
        "highest_score": None,
        "most_recent_score": None,
        "by_category": {},
        "by_dimension": {},
        "strongest_dimension": None,
        "weakest_dimension": None,
        "progress": [],
        "progress_sufficient": False,
    }


def build_summary(total_interviews: int, completed_interviews: int, evaluations: list) -> dict:
    """evaluations: list of dicts with category, difficulty, total_score,
    relevance_score, correctness_score, completeness_score, clarity_score,
    evaluated_at - already filtered to one account's own interviews, same
    shape storage.get_user_recommendation_data() returns."""
    if not evaluations:
        return _empty_summary(total_interviews, completed_interviews)

    scores = [e["total_score"] for e in evaluations]
    ordered = sorted(evaluations, key=lambda e: e["evaluated_at"])

    by_category = {}
    for category in sorted({e["category"] for e in evaluations}):  # fixed order -> deterministic
        cat_scores = [e["total_score"] for e in evaluations if e["category"] == category]
        by_category[category] = {"count": len(cat_scores), "average_score": round(mean(cat_scores), 1)}

    by_dimension = {}
    for field in DIMENSION_FIELDS:
        name, maximum, _tip = recommendations.DIMENSION_INFO[field]
        vals = [e[field] for e in evaluations]
        by_dimension[field] = {"label": name, "average": round(mean(vals), 1), "max": maximum}

    strongest = weakest = None
    if len(evaluations) >= recommendations.MIN_SAMPLES_FOR_TREND:
        ratios = {f: by_dimension[f]["average"] / by_dimension[f]["max"] for f in DIMENSION_FIELDS}
        strongest = max(DIMENSION_FIELDS, key=lambda f: (ratios[f], f))
        weakest = min(DIMENSION_FIELDS, key=lambda f: (ratios[f], f))

    progress = [{"evaluated_at": e["evaluated_at"], "score": e["total_score"]} for e in ordered]

    return {
        "total_interviews": total_interviews,
        "completed_interviews": completed_interviews,
        "evaluated_answers": len(evaluations),
        "completion_rate": round(completed_interviews / total_interviews, 3) if total_interviews else None,
        "average_score": round(mean(scores), 1),
        "highest_score": max(scores),
        "most_recent_score": ordered[-1]["total_score"],
        "by_category": by_category,
        "by_dimension": by_dimension,
        "strongest_dimension": strongest,
        "weakest_dimension": weakest,
        "progress": progress,
        "progress_sufficient": len(progress) >= 2,  # a single point can't show a trend
    }
