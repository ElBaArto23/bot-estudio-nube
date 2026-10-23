"""Lógica de estudio pura: sin red, sin Azure y sin Telegram.

Usa repetición espaciada tipo Leitner: cada pregunta tiene una "caja" (0 a 5).
Acertar sube de caja y la pregunta tarda más en volver; fallar la manda a la
caja 1 y vuelve al día siguiente. Al ser puro, todo se prueba sin infraestructura.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Mapping, Sequence

MAX_BOX = 5
# Días que deben pasar antes de volver a preguntar, según la caja.
INTERVAL_DAYS = {0: 0, 1: 1, 2: 2, 3: 4, 4: 8, 5: 16}
MASTERED_BOX = 4
# Telegram limita callback_data a 64 bytes y el prefijo ocupa 5 ("show:").
MAX_ID_LENGTH = 40

_NEVER = date(1970, 1, 1)


@dataclass(frozen=True)
class Question:
    id: str
    topic: str
    question: str
    answer: str


@dataclass(frozen=True)
class Progress:
    """Avance de una pregunta concreta."""

    box: int = 0
    last_seen: date | None = None
    ok: int = 0
    bad: int = 0


@dataclass(frozen=True)
class Profile:
    """Avance global de la persona."""

    streak: int = 0
    best_streak: int = 0
    last_day: date | None = None
    total_ok: int = 0
    total_bad: int = 0


def load_questions(path: str | Path) -> list[Question]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    questions = [Question(**item) for item in raw]
    ids = [q.id for q in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("Hay ids de pregunta repetidos")
    too_long = [i for i in ids if len(i) > MAX_ID_LENGTH]
    if too_long:
        raise ValueError(f"Ids demasiado largos (máx. {MAX_ID_LENGTH}): {too_long}")
    return questions


def due_date(progress: Progress) -> date:
    """Día a partir del cual la pregunta toca de nuevo. Las nuevas tocan ya."""
    if progress.last_seen is None:
        return _NEVER
    return progress.last_seen + timedelta(days=INTERVAL_DAYS[progress.box])


def pick_question(
    questions: Sequence[Question],
    progress: Mapping[str, Progress],
    rng: random.Random,
    exclude: str | None = None,
) -> Question:
    """Elige la pregunta que lleva más tiempo pendiente (empates al azar)."""
    pool = [q for q in questions if q.id != exclude] or list(questions)
    if not pool:
        raise ValueError("No hay preguntas cargadas")

    def due(q: Question) -> date:
        return due_date(progress.get(q.id, Progress()))

    earliest = min(due(q) for q in pool)
    return rng.choice([q for q in pool if due(q) == earliest])


def grade(progress: Progress, correct: bool, today: date) -> Progress:
    if correct:
        return replace(
            progress,
            box=min(progress.box + 1, MAX_BOX),
            last_seen=today,
            ok=progress.ok + 1,
        )
    return replace(progress, box=1, last_seen=today, bad=progress.bad + 1)


def update_profile(profile: Profile, correct: bool, today: date) -> Profile:
    if profile.last_day == today:
        streak = profile.streak
    elif profile.last_day == today - timedelta(days=1):
        streak = profile.streak + 1
    else:
        streak = 1
    return replace(
        profile,
        streak=streak,
        best_streak=max(profile.best_streak, streak),
        last_day=today,
        total_ok=profile.total_ok + (1 if correct else 0),
        total_bad=profile.total_bad + (0 if correct else 1),
    )


def current_streak(profile: Profile, today: date) -> int:
    """Racha vigente: si ayer no estudiaste, la racha ya se rompió."""
    if profile.last_day in (today, today - timedelta(days=1)):
        return profile.streak
    return 0


def format_stats(
    profile: Profile,
    progress: Mapping[str, Progress],
    questions: Sequence[Question],
    today: date,
) -> str:
    seen = sum(1 for q in questions if progress.get(q.id, Progress()).last_seen)
    mastered = sum(
        1 for q in questions if progress.get(q.id, Progress()).box >= MASTERED_BOX
    )
    total = profile.total_ok + profile.total_bad
    accuracy = f"{round(100 * profile.total_ok / total)} %" if total else "sin datos"
    return (
        f"🔥 Racha: {current_streak(profile, today)} día(s) (mejor: {profile.best_streak})\n"
        f"📖 Vistas: {seen} de {len(questions)}\n"
        f"🎓 Dominadas: {mastered}\n"
        f"🎯 Aciertos: {accuracy} ({profile.total_ok} de {total})"
    )
