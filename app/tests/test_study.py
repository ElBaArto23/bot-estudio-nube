import random
from datetime import date, timedelta
from pathlib import Path

import pytest

from study import (
    MAX_BOX,
    Profile,
    Progress,
    Question,
    current_streak,
    format_stats,
    grade,
    load_questions,
    pick_question,
    update_profile,
)

TODAY = date(2026, 10, 23)
QUESTIONS_FILE = Path(__file__).parent.parent / "questions.json"


def q(qid: str) -> Question:
    return Question(id=qid, topic="t", question=f"pregunta {qid}", answer="respuesta")


def test_questions_file_is_valid():
    questions = load_questions(QUESTIONS_FILE)
    assert len(questions) >= 10
    assert all(item.question and item.answer for item in questions)


def test_duplicate_ids_are_rejected(tmp_path):
    f = tmp_path / "q.json"
    f.write_text(
        '[{"id":"a","topic":"t","question":"?","answer":"!"},'
        '{"id":"a","topic":"t","question":"?","answer":"!"}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="repetidos"):
        load_questions(f)


def test_long_ids_are_rejected(tmp_path):
    f = tmp_path / "q.json"
    f.write_text(
        '[{"id":"' + "x" * 41 + '","topic":"t","question":"?","answer":"!"}]', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="largos"):
        load_questions(f)


def test_unseen_questions_come_before_seen_ones():
    progress = {"a": Progress(box=1, last_seen=TODAY)}
    for seed in range(20):
        chosen = pick_question([q("a"), q("b")], progress, random.Random(seed))
        assert chosen.id == "b"


def test_overdue_question_beats_recent_one():
    progress = {
        "a": Progress(box=1, last_seen=TODAY - timedelta(days=10)),
        "b": Progress(box=1, last_seen=TODAY),
    }
    assert pick_question([q("a"), q("b")], progress, random.Random(1)).id == "a"


def test_exclude_avoids_repeating_the_last_question():
    assert pick_question([q("a"), q("b")], {}, random.Random(1), exclude="a").id == "b"


def test_exclude_is_ignored_when_it_is_the_only_question():
    assert pick_question([q("a")], {}, random.Random(1), exclude="a").id == "a"


def test_correct_answer_moves_up_and_is_capped():
    p = Progress()
    for _ in range(10):
        p = grade(p, True, TODAY)
    assert p.box == MAX_BOX
    assert p.ok == 10 and p.last_seen == TODAY


def test_wrong_answer_resets_to_box_one():
    p = grade(Progress(box=4, ok=3), False, TODAY)
    assert p.box == 1 and p.bad == 1 and p.ok == 3


def test_streak_grows_on_consecutive_days():
    profile = Profile()
    for offset in range(3):
        profile = update_profile(profile, True, TODAY + timedelta(days=offset))
    assert profile.streak == 3 and profile.best_streak == 3


def test_same_day_does_not_increase_streak():
    profile = update_profile(Profile(), True, TODAY)
    profile = update_profile(profile, False, TODAY)
    assert profile.streak == 1
    assert profile.total_ok == 1 and profile.total_bad == 1


def test_gap_resets_streak_but_keeps_best():
    profile = update_profile(Profile(), True, TODAY)
    profile = update_profile(profile, True, TODAY + timedelta(days=1))
    profile = update_profile(profile, True, TODAY + timedelta(days=5))
    assert profile.streak == 1 and profile.best_streak == 2


def test_current_streak_expires_when_a_day_is_missed():
    profile = Profile(streak=4, best_streak=4, last_day=TODAY - timedelta(days=2))
    assert current_streak(profile, TODAY) == 0
    assert current_streak(Profile(streak=4, last_day=TODAY - timedelta(days=1)), TODAY) == 4


def test_stats_text_without_data():
    text = format_stats(Profile(), {}, [q("a"), q("b")], TODAY)
    assert "Vistas: 0 de 2" in text
    assert "sin datos" in text
