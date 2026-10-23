#!/usr/bin/env bash
# Crea terraform/backend_ci.tf para usar el estado remoto en Azure Storage.
# Lo usan los workflows; en local no hace falta (el estado queda en un archivo).
# Requiere las variables de entorno TFSTATE_RG y TFSTATE_SA.
set -euo pipefail

: "${TFSTATE_RG:?Falta TFSTATE_RG}"
: "${TFSTATE_SA:?Falta TFSTATE_SA}"

target="$(dirname "$0")/../terraform/backend_ci.tf"
cat > "$target" <<EOF
terraform {
  backend "azurerm" {
    resource_group_name  = "${TFSTATE_RG}"
    storage_account_name = "${TFSTATE_SA}"
    container_name       = "tfstate"
    key                  = "bot-estudio.tfstate"
    use_azuread_auth     = true
  }
}
EOF
echo "Backend remoto escrito en terraform/backend_ci.tf (${TFSTATE_SA}/tfstate)"
