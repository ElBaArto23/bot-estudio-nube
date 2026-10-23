"""Validación y procesamiento del webhook, separados de Azure Functions para poder probarlos."""
from __future__ import annotations

import hmac
import json
import logging
import os
from typing import Any, Callable, Mapping

log = logging.getLogger(__name__)

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
_KV_PREFIX = "@Microsoft.KeyVault"


def is_configured(value: str | None) -> bool:
    """False si falta o si Azure no pudo resolver la referencia a Key Vault.

    Cuando una referencia falla, la app recibe el texto literal "@Microsoft.KeyVault(...)".
    """
    return bool(value) and not value.startswith(_KV_PREFIX)


def health_payload(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Diagnóstico sin revelar valores: solo si cada ajuste llegó o no."""
    env = os.environ if env is None else env
    return {
        "status": "ok",
        "token_configured": is_configured(env.get("TELEGRAM_BOT_TOKEN")),
        "webhook_secret_configured": is_configured(env.get("TELEGRAM_WEBHOOK_SECRET")),
        "owner_configured": bool(env.get("OWNER_TELEGRAM_ID")),
    }


def process_webhook(
    *,
    headers: Mapping[str, str],
    body: bytes | str,
    expected_secret: str | None,
    handle: Callable[[dict[str, Any]], None],
) -> tuple[int, str]:
    """Devuelve (código HTTP, texto). Telegram reintenta si no recibe 200."""
    if not is_configured(expected_secret):
        log.error("TELEGRAM_WEBHOOK_SECRET sin configurar o sin resolver desde Key Vault")
        return 503, "webhook no configurado"

    received = headers.get(SECRET_HEADER, "")
    if not hmac.compare_digest(received.encode(), (expected_secret or "").encode()):
        log.warning("Webhook rechazado: secreto incorrecto")
        return 401, "no autorizado"

    try:
        update = json.loads(body)
    except ValueError:
        return 400, "JSON inválido"

    try:
        handle(update)
    except Exception:
        # Respondemos 200 igualmente: si no, Telegram reintentaría el mismo update
        # en bucle. El error queda en Application Insights.
        log.exception("Error procesando el update")
    return 200, "ok"
