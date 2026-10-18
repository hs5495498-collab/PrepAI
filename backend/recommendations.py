"""Deterministic, rule-based recommendation engine (Phase 9).

Takes an account's own evaluation history (already fetched and ownership-
filtered by storage.get_user_recommendation_data) and returns a short,
ordered list of recommendations. No AI calls happen here at all - this
module reuses real persisted evaluation data as its only input and is
fully deterministic: the same input always produces the same output in
the same order, which is also what the test suite checks.

Every recommendation is grounded in real data and says so via its
`evidence` list, or is explicitly marked evidence_level="generic" when
there isn't enough history yet to say anything specific. Nothing here
invents a score, a trend, or a weakness that isn't actually present in
the evaluations passed in.
"""
from statistics import mean

# --- Documented thresholds ---
# Reuses the app's own existing pass/fail line (P.passMark in data.js) so
# "weak" means the same thing here as it already does everywhere else in
# the UI, instead of inventing a second, inconsistent number.
WEAK_SCORE_THRESHOLD = 60
# Comfortably above the pass mark - only reached by consistently strong
# answers, which is what justifies suggesting a harder difficulty.
STRONG_SCORE_THRESHOLD = 85
# Below 3 data points, one unusually good or bad answer can swing an
# average entirely - 3 is the smallest sample size where "most answers
# agree" starts to mean something for a lightweight heuristic like this.
MIN_SAMPLES_FOR_TREND = 3
# A dimension sub-score below 60% of its own maximum counts as weak for
# that dimension - the same ratio as WEAK_SCORE_THRESHOLD/100, applied
# per-dimension instead of to the total.
WEAK_DIMENSION_RATIO = 0.6
# A max-min spread of 40+ points among same-category scores is treated as
# "inconsistent" - large enough that it can't just be ordinary noise
# between two otherwise-similar answers.
INCONSISTENCY_SPREAD = 40
# Only the most recent N evaluations are considered "recent" for trend and
# consistency checks - recent enough to reflect current performance, but
# large enough that a 3-category breakdown still has room for a few
# samples per category.
RECENT_WINDOW = 10
# Keeps the results shortlist in line with the rest of the app's existing
# "What to Focus On Next"-style lists (2-3 items).
MAX_RECOMMENDATIONS = 4

CATEGORY_LABELS = {"technical": "Technical", "hr": "HR", "behavioral": "Behavioral"}
NEXT_DIFFICULTY = {"easy": "medium", "medium": "hard"}
DIMENSION_INFO = {
    "relevance_score": ("Relevance", 30, "Answering exactly what was asked, without drifting off-topic."),
    "correctness_score": ("Correctness", 35, "Technical or factual accuracy, and soundness of your reasoning."),
    "completeness_score": ("Completeness", 25, "Covering the important points without leaving key parts out."),
    "clarity_score": ("Clarity", 10, "Organizing your answer so it's easy to follow."),
}

PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


def _recent(evaluations):
    return evaluations[-RECENT_WINDOW:] if len(evaluations) > RECENT_WINDOW else list(evaluations)


def _no_history_recommendation():
    return {
        "key": "start_first_interview",
        "title": "Complete your first practice interview",
        "explanation": "Recommendations here are based on your own evaluated answers, and you don't have any yet.",
        "reason": "No completed interviews were found on your account.",
        "category": None,
        "difficulty": None,
        "action": "Start a practice interview to begin building your history.",
        "priority": "high",
        "evidence": [],
        "evidence_level": "generic",
    }


def _no_evaluations_recommendation(completed_interviews: int):
    return {
        "key": "evaluate_an_answer",
        "title": "Get AI feedback on a past answer",
        "explanation": "You've completed {} interview{}, but none of your answers have been evaluated yet - "
                        "that's what personalized recommendations are based on.".format(
                            completed_interviews, "" if completed_interviews == 1 else "s"
                        ),
        "reason": "No evaluated answers were found on your account.",
        "category": None,
        "difficulty": None,
        "action": "Open a past result and click \"Evaluate with AI\" on an answered question.",
        "priority": "medium",
        "evidence": [],
        "evidence_level": "generic",
    }


def _category_recommendations(recent):
    by_category = {}
    for e in recent:
        by_category.setdefault(e["category"], []).append(e["total_score"])

    out = []
    for category in sorted(by_category):  # fixed order -> deterministic
        scores = by_category[category]
        avg = mean(scores)
        label = CATEGORY_LABELS.get(category, category)
        if avg < WEAK_SCORE_THRESHOLD:
            sufficient = len(scores) >= MIN_SAMPLES_FOR_TREND
            out.append({
                "key": "weak_category_" + category,
                "title": "Practise more {} questions".format(label),
                "explanation": "Your {} answers have been averaging below a passing score.".format(label)
                                if sufficient else
                                "Your {} answers so far have scored low, though this is based on very few answers.".format(label),
                "reason": "Average score in {} is {}/100 across {} evaluated answer{}.".format(
                    label, round(avg), len(scores), "" if len(scores) == 1 else "s"
                ),
                "category": category,
                "difficulty": None,
                "action": "Start a {} practice interview and focus on the areas noted in your past feedback.".format(label),
                "priority": "high" if sufficient else "medium",
                "evidence": ["Average {} score: {}/100 across {} evaluated answer{}".format(
                    label, round(avg), len(scores), "" if len(scores) == 1 else "s"
                )],
                "evidence_level": "data" if sufficient else "limited",
            })
        elif avg >= STRONG_SCORE_THRESHOLD and len(scores) >= MIN_SAMPLES_FOR_TREND:
            # Only suggest a harder difficulty when we also know which
            # difficulty they've actually been practising at.
            difficulties = [e["difficulty"] for e in recent if e["category"] == category]
            common_difficulty = max(set(difficulties), key=difficulties.count)
            next_difficulty = NEXT_DIFFICULTY.get(common_difficulty)
            if next_difficulty:
                out.append({
                    "key": "increase_difficulty_" + category,
                    "title": "Try {} at a harder difficulty".format(label),
                    "explanation": "You've been consistently scoring well on {} questions.".format(label),
                    "reason": "Average score in {} is {}/100 across {} evaluated answer{} at {} difficulty.".format(
                        label, round(avg), len(scores), "" if len(scores) == 1 else "s", common_difficulty
                    ),
                    "category": category,
                    "difficulty": next_difficulty,
                    "action": "Start a {} practice interview at {} difficulty.".format(label, next_difficulty),
                    "priority": "low",
                    "evidence": ["Average {} score: {}/100 across {} evaluated answer{} at {} difficulty".format(
                        label, round(avg), len(scores), "" if len(scores) == 1 else "s", common_difficulty
                    )],
                    "evidence_level": "data",
                })

        if len(scores) >= MIN_SAMPLES_FOR_TREND and (max(scores) - min(scores)) >= INCONSISTENCY_SPREAD:
            out.append({
                "key": "inconsistent_" + category,
                "title": "Review your inconsistent {} results".format(label),
                "explanation": "Your {} scores have varied a lot between attempts.".format(label),
                "reason": "{} scores ranged from {} to {} across {} evaluated answers.".format(
                    label, min(scores), max(scores), len(scores)
                ),
                "category": category,
                "difficulty": None,
                "action": "Compare your strongest and weakest {} answers to see what made the difference.".format(label),
                "priority": "medium",
                "evidence": ["{} score range: {}-{} across {} evaluated answers".format(
                    label, min(scores), max(scores), len(scores)
                )],
                "evidence_level": "data",
            })
    return out


def _dimension_recommendations(recent):
    out = []
    for field in ["relevance_score", "correctness_score", "completeness_score", "clarity_score"]:  # fixed order
        name, maximum, tip = DIMENSION_INFO[field]
        scores = [e[field] for e in recent]
        if len(scores) < MIN_SAMPLES_FOR_TREND:
            continue
        avg = mean(scores)
        if avg < WEAK_DIMENSION_RATIO * maximum:
            out.append({
                "key": "weak_dimension_" + field,
                "title": "Work on {}".format(name.lower()),
                "explanation": tip,
                "reason": "Average {} score is {}/{} across {} evaluated answers.".format(name, round(avg, 1), maximum, len(scores)),
                "category": None,
                "difficulty": None,
                "action": "Keep this in mind on your next practice interview: {}".format(tip.lower()),
                "priority": "medium",
                "evidence": ["Average {} score: {}/{} across {} evaluated answers".format(name, round(avg, 1), maximum, len(scores))],
                "evidence_level": "data",
            })
    return out


def build_recommendations(completed_interviews: int, evaluations: list) -> list:
    """evaluations: list of dicts with category, difficulty, total_score,
    relevance_score, correctness_score, completeness_score, clarity_score,
    evaluated_at - already filtered to this one account's own interviews.
    Returns at most MAX_RECOMMENDATIONS recommendation dicts, most
    important first, in a deterministic order for the same input."""
    if completed_interviews == 0:
        return [_no_history_recommendation()]
    if not evaluations:
        return [_no_evaluations_recommendation(completed_interviews)]

    recent = _recent(evaluations)
    candidates = _category_recommendations(recent) + _dimension_recommendations(recent)
    if not candidates:
        return []
    candidates.sort(key=lambda r: (PRIORITY_RANK[r["priority"]], r["key"]))
    return candidates[:MAX_RECOMMENDATIONS]
