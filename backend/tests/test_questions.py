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
    questions_list, insufficient = pick_questions("technical", "hard", 3)
    texts = [text for _qid, text in questions_list]
    hard_texts = [text for d, text in DEMO_QUESTION_BANK["technical"] if d == "hard"]
    assert texts == hard_texts[:3]
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
