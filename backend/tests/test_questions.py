import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import questions
from questions import DEMO_QUESTION_BANK, pick_questions


def test_bank_has_fifteen_distinct_questions_per_category():
    for category, entries in DEMO_QUESTION_BANK.items():
        texts = [text for _d, text in entries]
        assert len(texts) == 15, category
        assert len(set(texts)) == 15, "duplicate question text in " + category


def test_full_count_request_returns_no_duplicates():
    questions_list, insufficient = pick_questions("technical", "medium", 15)
    texts = [text for _qid, text in questions_list]
    assert len(texts) == 15
    assert len(set(texts)) == 15
    assert insufficient is False


def test_small_count_prefers_matching_difficulty_first():
    # The exact order within the matching-difficulty pool is now shuffled
    # per call (see the variation tests below), so this checks the real
    # invariant - every returned question comes from the matching-difficulty
    # pool before any other-difficulty question would be needed - rather
    # than a specific bank order.
    questions_list, insufficient = pick_questions("technical", "hard", 3, rng=random.Random(42))
    texts = [text for _qid, text in questions_list]
    hard_texts = {text for d, text in DEMO_QUESTION_BANK["technical"] if d == "hard"}
    assert len(texts) == 3
    assert set(texts).issubset(hard_texts)
    assert insufficient is False


def test_selection_is_reproducible_with_a_seeded_rng():
    first, _ = pick_questions("technical", "medium", 5, rng=random.Random(7))
    second, _ = pick_questions("technical", "medium", 5, rng=random.Random(7))
    assert first == second


def test_different_seeds_can_select_different_questions():
    # Variation between sessions: two different seeds, over enough runs,
    # must not always land on the exact same 5-question selection out of a
    # 15-question pool. Using many seeds instead of just two avoids a flaky
    # test that could coincidentally pick the same subset once.
    selections = set()
    for seed in range(20):
        picked, _ = pick_questions("technical", "medium", 5, rng=random.Random(seed))
        selections.add(tuple(text for _qid, text in picked))
    assert len(selections) > 1


def test_exclude_texts_avoids_recent_questions_when_enough_alternatives_exist():
    pool = [text for d, text in DEMO_QUESTION_BANK["technical"] if d == "medium"]
    exclude = set(pool[:3])  # 3 of the 5 "medium" questions were asked recently
    questions_list, insufficient = pick_questions(
        "technical", "medium", 5, rng=random.Random(1), exclude_texts=exclude
    )
    texts = {text for _qid, text in questions_list}
    assert not (texts & exclude), "a recently-asked question was repeated even though enough alternatives existed"
    assert insufficient is False


def test_exclude_texts_is_dropped_when_it_would_leave_too_few_questions():
    # Excluding 13 of the 15 technical questions leaves only 2 - not enough
    # to satisfy a request for 5 - so the exclusion must be dropped for this
    # call rather than ever returning fewer than requested just to honor it.
    all_texts = [text for _d, text in DEMO_QUESTION_BANK["technical"]]
    exclude = set(all_texts[:13])
    questions_list, insufficient = pick_questions(
        "technical", "medium", 5, rng=random.Random(2), exclude_texts=exclude
    )
    assert len(questions_list) == 5
    assert insufficient is False


def test_count_larger_than_difficulty_pool_fills_from_other_difficulties_without_repeats():
    # Only 5 "easy" technical questions exist; requesting 8 must not repeat
    # any of them - the extra 3 must come from medium/hard instead.
    questions_list, insufficient = pick_questions("technical", "easy", 8)
    texts = [text for _qid, text in questions_list]
    assert len(texts) == 8
    assert len(set(texts)) == 8
    assert insufficient is False


def test_insufficient_bank_returns_all_available_without_padding(monkeypatch):
    small_bank = {"technical": [("easy", "Only question available?")]}
    monkeypatch.setattr(questions, "DEMO_QUESTION_BANK", small_bank)
    questions_list, insufficient = pick_questions("technical", "easy", 5)
    assert insufficient is True
    assert len(questions_list) == 1
    assert questions_list == [("q1", "Only question available?")]
