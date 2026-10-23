"""Orquestación del bot: convierte un update de Telegram en respuestas.

No conoce Azure ni `requests`: recibe el almacén y el mensajero por inyección,
así que se prueba entero con objetos falsos.
"""
from __future__ import annotations

import logging
import random
from datetime import date
from typing import Any, Mapping, Protocol, Sequence

from study import (
    Profile,
    Progress,
    Question,
    current_streak,
    format_stats,
    grade,
    pick_question,
    update_profile,
)

log = logging.getLogger(__name__)

HELP_TEXT = (
    "Soy tu bot de estudio de nube y desarrollo.\n\n"
    "/pregunta - una pregunta de repaso\n"
    "/racha - tu racha y tu progreso\n"
    "/ayuda - este mensaje\n\n"
    "Cada día recibes una pregunta automática. Las que fallas vuelven antes."
)


class Store(Protocol):
    def get_profile(self, user_id: int) -> Profile: ...
    def save_profile(self, user_id: int, profile: Profile) -> None: ...
    def get_progress(self, user_id: int) -> dict[str, Progress]: ...
    def save_progress(self, user_id: int, question_id: str, progress: Progress) -> None: ...


class Messenger(Protocol):
    def send_message(
        self, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None
    ) -> None: ...
    def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> None: ...
    def answer_callback(self, callback_id: str, text: str = "") -> None: ...


def _keyboard(*buttons: tuple[str, str]) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": label, "callback_data": data} for label, data in buttons]
        ]
    }


def _card(question: Question, *, with_answer: bool = False) -> str:
    text = f"📚 [{question.topic}]\n\n{question.question}"
    if with_answer:
        text += f"\n\n💡 {question.answer}"
    return text


class StudyBot:
    def __init__(
        self,
        *,
        owner_id: int,
        store: Store,
        messenger: Messenger,
        questions: Sequence[Question],
        rng: random.Random | None = None,
    ) -> None:
        self._owner_id = owner_id
        self._store = store
        self._messenger = messenger
        self._questions = list(questions)
        self._by_id = {q.id: q for q in self._questions}
        self._rng = rng or random.Random()

    # ------------------------------------------------------------------ entrada
    def handle_update(self, update: Mapping[str, Any], today: date) -> None:
        if "callback_query" in update:
            self._handle_callback(update["callback_query"], today)
        elif "message" in update:
            self._handle_message(update["message"], today)
        else:
            log.info("Update ignorado (tipo no soportado): %s", sorted(update.keys()))

    def send_daily_question(self, today: date) -> bool:
        """Pregunta del día. No molesta si ya estudiaste hoy. Devuelve si envió."""
        if self._store.get_profile(self._owner_id).last_day == today:
            log.info("Pregunta diaria omitida: ya hay actividad hoy")
            return False
        self._ask(self._owner_id)
        return True

    # ---------------------------------------------------------------- mensajes
    def _handle_message(self, message: Mapping[str, Any], today: date) -> None:
        sender = (message.get("from") or {}).get("id")
        if not self._authorized(sender):
            return
        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()
        # "/pregunta@MiBot" en grupos: nos quedamos con el comando.
        command = text.split()[0].split("@")[0].lower() if text else ""

        if command in ("/start", "/ayuda", "/help"):
            self._messenger.send_message(chat_id, HELP_TEXT)
        elif command == "/pregunta":
            self._ask(chat_id)
        elif command == "/racha":
            stats = format_stats(
                self._store.get_profile(sender),
                self._store.get_progress(sender),
                self._questions,
                today,
            )
            self._messenger.send_message(chat_id, stats)
        else:
            self._messenger.send_message(chat_id, "No te entendí. Prueba con /ayuda.")

    def _ask(self, chat_id: int) -> None:
        progress = self._store.get_progress(self._owner_id)
        question = pick_question(self._questions, progress, self._rng)
        self._messenger.send_message(
            chat_id,
            _card(question),
            _keyboard(("Ver respuesta", f"show:{question.id}")),
        )

    # ---------------------------------------------------------------- botones
    def _handle_callback(self, callback: Mapping[str, Any], today: date) -> None:
        sender = (callback.get("from") or {}).get("id")
        if not self._authorized(sender):
            return
        callback_id = callback.get("id", "")
        message = callback.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        message_id = message.get("message_id")
        action, _, question_id = (callback.get("data") or "").partition(":")
        question = self._by_id.get(question_id)

        if question is None or action not in ("show", "ok", "bad") or None in (chat_id, message_id):
            self._messenger.answer_callback(callback_id, "Esa pregunta ya no existe.")
            return

        if action == "show":
            self._messenger.edit_message(
                chat_id,
                message_id,
                _card(question, with_answer=True),
                _keyboard(("✅ La sabía", f"ok:{question.id}"), ("❌ No la sabía", f"bad:{question.id}")),
            )
        else:
            self._register_result(sender, question, action == "ok", today)
            profile = self._store.get_profile(sender)
            mark = "✅" if action == "ok" else "❌"
            self._messenger.edit_message(
                chat_id,
                message_id,
                f"{_card(question, with_answer=True)}\n\n{mark} Registrado. "
                f"Racha: {current_streak(profile, today)} día(s).",
            )
        self._messenger.answer_callback(callback_id)

    def _register_result(self, user_id: int, question: Question, correct: bool, today: date) -> None:
        progress = self._store.get_progress(user_id).get(question.id, Progress())
        self._store.save_progress(user_id, question.id, grade(progress, correct, today))
        self._store.save_profile(
            user_id, update_profile(self._store.get_profile(user_id), correct, today)
        )

    # --------------------------------------------------------------- seguridad
    def _authorized(self, sender_id: int | None) -> bool:
        if sender_id == self._owner_id:
            return True
        # Solo el id numérico, nunca el contenido del mensaje.
        log.warning("Update ignorado de usuario no autorizado (id=%s)", sender_id)
        return False
