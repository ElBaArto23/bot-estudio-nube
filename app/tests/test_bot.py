import random
from datetime import date

import pytest

from bot import HELP_TEXT, StudyBot
from storage import MemoryStore
from study import Question

OWNER = 111
STRANGER = 999
TODAY = date(2026, 10, 23)

QUESTIONS = [
    Question(id="uno", topic="Azure", question="¿Uno?", answer="Sí, uno."),
    Question(id="dos", topic="Azure", question="¿Dos?", answer="Sí, dos."),
]


class FakeMessenger:
    def __init__(self):
        self.sent = []
        self.edited = []
        self.answered = []

    def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append((chat_id, text, reply_markup))

    def edit_message(self, chat_id, message_id, text, reply_markup=None):
        self.edited.append((chat_id, message_id, text, reply_markup))

    def answer_callback(self, callback_id, text=""):
        self.answered.append((callback_id, text))


@pytest.fixture
def env():
    store, messenger = MemoryStore(), FakeMessenger()
    bot = StudyBot(
        owner_id=OWNER,
        store=store,
        messenger=messenger,
        questions=QUESTIONS,
        rng=random.Random(0),
    )
    return bot, store, messenger


def message(text, sender=OWNER):
    return {"message": {"from": {"id": sender}, "chat": {"id": sender}, "text": text}}


def callback(data, sender=OWNER):
    return {
        "callback_query": {
            "id": "cb1",
            "from": {"id": sender},
            "data": data,
            "message": {"chat": {"id": sender}, "message_id": 7},
        }
    }


def test_stranger_gets_no_reply_and_nothing_is_stored(env):
    bot, store, messenger = env
    bot.handle_update(message("/pregunta", STRANGER), TODAY)
    bot.handle_update(callback("ok:uno", STRANGER), TODAY)
    assert messenger.sent == [] and messenger.edited == [] and messenger.answered == []
    assert store.get_progress(STRANGER) == {}


def test_start_shows_help(env):
    bot, _, messenger = env
    bot.handle_update(message("/start"), TODAY)
    assert messenger.sent[0][1] == HELP_TEXT


def test_command_with_bot_name_suffix_is_understood(env):
    bot, _, messenger = env
    bot.handle_update(message("/pregunta@MiBot"), TODAY)
    assert "📚" in messenger.sent[0][1]


def test_unknown_text_gets_a_hint(env):
    bot, _, messenger = env
    bot.handle_update(message("hola"), TODAY)
    assert "/ayuda" in messenger.sent[0][1]


def test_question_comes_with_a_show_button(env):
    bot, _, messenger = env
    bot.handle_update(message("/pregunta"), TODAY)
    chat_id, text, markup = messenger.sent[0]
    assert chat_id == OWNER and "¿" in text
    data = markup["inline_keyboard"][0][0]["callback_data"]
    assert data in ("show:uno", "show:dos")


def test_show_reveals_the_answer_with_grading_buttons(env):
    bot, _, messenger = env
    bot.handle_update(callback("show:uno"), TODAY)
    _, message_id, text, markup = messenger.edited[0]
    assert message_id == 7 and "Sí, uno." in text
    data = [b["callback_data"] for b in markup["inline_keyboard"][0]]
    assert data == ["ok:uno", "bad:uno"]
    assert messenger.answered == [("cb1", "")]


def test_correct_answer_is_saved_and_streak_starts(env):
    bot, store, messenger = env
    bot.handle_update(callback("ok:uno"), TODAY)
    progress = store.get_progress(OWNER)["uno"]
    assert progress.box == 1 and progress.ok == 1 and progress.last_seen == TODAY
    assert store.get_profile(OWNER).streak == 1
    assert "Racha: 1" in messenger.edited[0][2]
    assert messenger.edited[0][3] == {"inline_keyboard": []} or messenger.edited[0][3] is None


def test_wrong_answer_is_saved(env):
    bot, store, _ = env
    bot.handle_update(callback("bad:dos"), TODAY)
    progress = store.get_progress(OWNER)["dos"]
    assert progress.box == 1 and progress.bad == 1
    assert store.get_profile(OWNER).total_bad == 1


def test_unknown_question_is_reported_not_crashed(env):
    bot, store, messenger = env
    bot.handle_update(callback("ok:no-existe"), TODAY)
    assert messenger.answered == [("cb1", "Esa pregunta ya no existe.")]
    assert store.get_progress(OWNER) == {}


def test_malformed_callback_is_reported(env):
    bot, _, messenger = env
    bot.handle_update(callback("basura"), TODAY)
    assert messenger.answered[0][1] == "Esa pregunta ya no existe."


def test_stats_after_one_answer(env):
    bot, _, messenger = env
    bot.handle_update(callback("ok:uno"), TODAY)
    bot.handle_update(message("/racha"), TODAY)
    text = messenger.sent[-1][1]
    assert "Racha: 1" in text and "Vistas: 1 de 2" in text and "100 %" in text


def test_daily_question_is_sent_when_nothing_studied_today(env):
    bot, _, messenger = env
    assert bot.send_daily_question(TODAY) is True
    assert messenger.sent[0][0] == OWNER


def test_daily_question_is_skipped_after_studying(env):
    bot, _, messenger = env
    bot.handle_update(callback("ok:uno"), TODAY)
    assert bot.send_daily_question(TODAY) is False
    assert messenger.sent == []


def test_unsupported_update_type_is_ignored(env):
    bot, _, messenger = env
    bot.handle_update({"edited_message": {}}, TODAY)
    assert messenger.sent == [] and messenger.edited == []
