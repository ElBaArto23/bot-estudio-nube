import pytest
import requests

from telegram import TelegramClient, TelegramError

TOKEN = "123456:SECRET-TOKEN-VALUE"


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("sin json")
        return self._body


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self.error:
            raise self.error
        return self.response


def test_send_message_posts_to_the_right_method_with_a_timeout():
    session = FakeSession(FakeResponse(200, {"ok": True, "result": {}}))
    TelegramClient(TOKEN, session=session).send_message(5, "hola")
    call = session.calls[0]
    assert call["url"].endswith("/sendMessage")
    assert call["json"] == {"chat_id": 5, "text": "hola"}
    assert call["timeout"] and call["timeout"] > 0


def test_network_error_never_leaks_the_token():
    # requests incluye la URL (con el token) en el texto de sus excepciones.
    leaky = requests.ConnectionError(f"Max retries exceeded with url: /bot{TOKEN}/sendMessage")
    client = TelegramClient(TOKEN, session=FakeSession(error=leaky))
    with pytest.raises(TelegramError) as info:
        client.send_message(5, "hola")
    assert TOKEN not in str(info.value)
    assert info.value.__cause__ is None and info.value.__suppress_context__


def test_http_error_reports_telegram_description_without_token():
    session = FakeSession(FakeResponse(400, {"ok": False, "description": "Bad Request: chat not found"}))
    with pytest.raises(TelegramError, match="chat not found") as info:
        TelegramClient(TOKEN, session=session).send_message(5, "hola")
    assert TOKEN not in str(info.value)


def test_non_json_error_body_is_handled():
    with pytest.raises(TelegramError, match="HTTP 502"):
        TelegramClient(TOKEN, session=FakeSession(FakeResponse(502))).send_message(5, "hola")


def test_edit_without_keyboard_removes_buttons():
    session = FakeSession(FakeResponse(200, {"ok": True, "result": True}))
    TelegramClient(TOKEN, session=session).edit_message(5, 9, "nuevo")
    assert session.calls[0]["json"]["reply_markup"] == {"inline_keyboard": []}


def test_long_text_is_truncated_to_telegram_limit():
    session = FakeSession(FakeResponse(200, {"ok": True, "result": {}}))
    TelegramClient(TOKEN, session=session).send_message(5, "x" * 5000)
    assert len(session.calls[0]["json"]["text"]) == 4096


def test_empty_callback_id_is_a_noop():
    session = FakeSession(FakeResponse(200, {"ok": True}))
    TelegramClient(TOKEN, session=session).answer_callback("")
    assert session.calls == []


def test_empty_token_is_rejected():
    with pytest.raises(ValueError):
        TelegramClient("")
