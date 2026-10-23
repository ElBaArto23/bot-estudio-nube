#!/usr/bin/env bash
# Deja el bot funcionando tras el primer despliegue:
#   1. guarda el token de BotFather en Key Vault (se pide oculto, no se muestra),
#   2. crea el secreto del webhook,
#   3. reinicia la Function App para que lea los secretos,
#   4. registra el webhook en Telegram.
#
# Uso (el comando exacto aparece en el resumen del flujo Deploy):
#   bash scripts/configure-bot.sh <grupo-recursos> <key-vault> <function-app>
#
# Necesita `az login` con tu usuario y el rol "Key Vault Secrets Officer" en el vault
# (Terraform te lo da si definiste ADMIN_OBJECT_ID). Para cambiar el token:
#   ROTATE_TOKEN=1 bash scripts/configure-bot.sh ...
set -euo pipefail

RG="${1:?Uso: bash scripts/configure-bot.sh <grupo-recursos> <key-vault> <function-app>}"
VAULT="${2:?Falta el nombre del Key Vault}"
APP="${3:?Falta el nombre de la Function App}"

secret_exists() {
  az keyvault secret show --vault-name "$VAULT" --name "$1" --query name -o tsv >/dev/null 2>&1
}

# 1 -------------------------------------------------------------------------
if secret_exists telegram-bot-token && [ "${ROTATE_TOKEN:-0}" != "1" ]; then
  echo "==> Token ya guardado en Key Vault (usa ROTATE_TOKEN=1 para reemplazarlo)"
else
  read -rsp "Pega el token de BotFather (no se mostrará): " TOKEN
  echo
  [ -n "$TOKEN" ] || { echo "El token está vacío." >&2; exit 1; }
  az keyvault secret set --vault-name "$VAULT" --name telegram-bot-token \
    --value "$TOKEN" --output none
  unset TOKEN
  echo "==> Token guardado en Key Vault"
fi

# 2 -------------------------------------------------------------------------
if ! secret_exists telegram-webhook-secret; then
  az keyvault secret set --vault-name "$VAULT" --name telegram-webhook-secret \
    --value "$(openssl rand -hex 32)" --output none
  echo "==> Secreto del webhook creado"
fi

# 3 -------------------------------------------------------------------------
echo "==> Reiniciando la Function App"
az functionapp restart --resource-group "$RG" --name "$APP" --output none
HOST="$(az functionapp show --resource-group "$RG" --name "$APP" --query defaultHostName -o tsv)"

echo "==> Esperando a que cargue los secretos (hasta 2 min)"
for _ in $(seq 1 12); do
  health="$(curl -sS --max-time 20 "https://${HOST}/api/health" || true)"
  if printf '%s' "$health" | grep -q '"token_configured": *true' \
     && printf '%s' "$health" | grep -q '"webhook_secret_configured": *true'; then
    break
  fi
  sleep 10
done
echo "    /api/health -> $health"
if ! printf '%s' "$health" | grep -q '"token_configured": *true'; then
  echo "AVISO: la app aún no ve el token. Revisa que tu usuario y la Function tengan acceso" >&2
  echo "       al Key Vault y vuelve a ejecutar este script en unos minutos." >&2
fi

# 4 -------------------------------------------------------------------------
# El token va en la URL, así que la petición se pasa a curl por stdin (-K -):
# no aparece en la lista de procesos ni se imprime.
TOKEN="$(az keyvault secret show --vault-name "$VAULT" --name telegram-bot-token --query value -o tsv)"
WEBHOOK_SECRET="$(az keyvault secret show --vault-name "$VAULT" --name telegram-webhook-secret --query value -o tsv)"

echo "==> Registrando el webhook en Telegram"
curl -sS --max-time 20 -K - <<EOF
url = "https://api.telegram.org/bot${TOKEN}/setWebhook"
data-urlencode = "url=https://${HOST}/api/telegram"
data-urlencode = "secret_token=${WEBHOOK_SECRET}"
data-urlencode = "allowed_updates=[\"message\",\"callback_query\"]"
data-urlencode = "drop_pending_updates=true"
EOF
echo
unset TOKEN WEBHOOK_SECRET

echo "Listo. Escríbele /start a tu bot en Telegram."
