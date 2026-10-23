"""Punto de entrada de Azure Functions (modelo de programación v2).

Solo conecta piezas: la lógica vive en bot.py, study.py, storage.py y webhook.py.
"""
from __future__ import annotations

import functools
import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import azure.functions as func

from bot import StudyBot
from storage import make_store
from study import load_questions
from telegram import TelegramClient
from webhook import SECRET_HEADER, health_payload, is_configured, process_webhook  # noqa: F401

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

QUESTIONS_PATH = Path(__file__).parent / "questions.json"


def _today() -> date:
    tz = ZoneInfo(os.environ.get("STUDY_TIMEZONE", "America/Bogota"))
    return datetime.now(tz).date()


@functools.lru_cache(maxsize=1)
def _bot() -> StudyBot:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not is_configured(token):
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN sin configurar o sin resolver: revisa el secreto en Key Vault"
        )
    return StudyBot(
        owner_id=int(os.environ["OWNER_TELEGRAM_ID"]),
        store=make_store(),
        messenger=TelegramClient(token),
        questions=load_questions(QUESTIONS_PATH),
    )


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(health_payload()), mimetype="application/json", status_code=200
    )


@app.route(route="telegram", methods=["POST"])
def telegram_webhook(req: func.HttpRequest) -> func.HttpResponse:
    status, text = process_webhook(
        headers=req.headers,
        body=req.get_body(),
        expected_secret=os.environ.get("TELEGRAM_WEBHOOK_SECRET"),
        handle=lambda update: _bot().handle_update(update, _today()),
    )
    return func.HttpResponse(text, status_code=status)


# La hora sale del ajuste DAILY_SCHEDULE (lo define Terraform), formato NCRONTAB en UTC.
@app.timer_trigger(schedule="%DAILY_SCHEDULE%", arg_name="timer", run_on_startup=False)
def daily_question(timer: func.TimerRequest) -> None:
    sent = _bot().send_daily_question(_today())
    logging.info("Pregunta diaria enviada: %s", sent)
