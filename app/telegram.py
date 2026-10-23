"""Cliente mínimo de la API de Telegram.

Punto de seguridad: el token viaja en la URL (/bot<TOKEN>/método). Las excepciones
de `requests` incluyen esa URL, así que se capturan y se vuelven a lanzar sin ella;
de lo contrario el token acabaría en los logs de Application Insights.
"""
from __future__ import annotations

from typing import Any

import requests

API_BASE = "https://api.telegram.org"
MAX_TEXT = 4096
DEFAULT_TIMEOUT = 10  # segundos: nunca llamar a un servicio externo sin límite


class TelegramError(Exception):
    """Error al hablar con Telegram. El mensaje nunca incluye el token."""


class TelegramClient:
    def __init__(
        self,
        token: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
    ) -> None:
        if not token:
            raise ValueError("Falta el token del bot")
        self._token = token
        self._timeout = timeout
        self._session = session or requests.Session()

    def _call(self, method: str, payload: dict[str, Any]) -> Any:
        url = f"{API_BASE}/bot{self._token}/{method}"
        try:
            response = self._session.post(url, json=payload, timeout=self._timeout)
        except requests.RequestException as exc:
            # `from None` corta la cadena de excepciones: la original lleva la URL.
            raise TelegramError(f"{method}: error de red ({type(exc).__name__})") from None
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code != 200 or not data.get("ok"):
            description = data.get("description", "sin descripción")
            raise TelegramError(f"{method}: HTTP {response.status_code} - {description}")
        return data.get("result")

    def send_message(
        self, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None
    ) -> None:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text[:MAX_TEXT]}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        self._call("sendMessage", payload)

    def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text[:MAX_TEXT],
            # Sin teclado explícito, quitamos los botones del mensaje.
            "reply_markup": reply_markup or {"inline_keyboard": []},
        }
        self._call("editMessageText", payload)

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        if not callback_id:
            return
        payload: dict[str, Any] = {"callback_query_id": callback_id}
        if text:
            payload["text"] = text
        self._call("answerCallbackQuery", payload)
