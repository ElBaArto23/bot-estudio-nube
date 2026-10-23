#!/usr/bin/env bash
# Comprueba que cada variable de entorno llegó con valor, sin mostrar el valor.
# Un Secret leído como Variable (o al revés) llega vacío: este paso lo hace visible.
#
#   bash scripts/check-config.sh AZURE_CLIENT_ID TFSTATE_RG ...
set -uo pipefail

missing=0
for name in "$@"; do
  if [ -n "${!name:-}" ]; then
    echo "$name definido: sí"
  else
    echo "::error::$name definido: NO. Créala en Settings > Secrets and variables > Actions > Variables."
    missing=1
  fi
done
exit "$missing"
