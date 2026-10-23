#!/usr/bin/env bash
# Preparación única. Ejecútalo en Azure Cloud Shell (Bash) con tu usuario:
#
#   bash scripts/bootstrap-github.sh <usuario/repositorio>
#
# Crea, de forma repetible (puedes volver a ejecutarlo sin duplicar nada):
#   1. Registro de los proveedores de recursos que usa el proyecto.
#   2. Grupo de recursos de la aplicación (estudio-rg) y otro para el estado de Terraform.
#   3. Cuenta de almacenamiento + contenedor para el estado remoto.
#   4. Una identidad para GitHub con OIDC: SIN contraseña y con permisos solo sobre
#      el grupo de recursos de la aplicación.
# Al final imprime las Variables (no Secrets) que debes crear en GitHub.
set -euo pipefail

REPO="${1:?Uso: bash scripts/bootstrap-github.sh <usuario/repositorio>}"
LOCATION="${LOCATION:-eastus}"
APP_RG="${APP_RG:-estudio-rg}"
STATE_RG="${STATE_RG:-tfstate-rg}"
IDENTITY_NAME="${IDENTITY_NAME:-github-bot-estudio}"

SUB_ID="$(az account show --query id -o tsv)"
TENANT_ID="$(az account show --query tenantId -o tsv)"
STATE_SA="tfstate$(printf '%s' "$SUB_ID" | sha1sum | cut -c1-10)"

echo "Suscripción: $SUB_ID"
echo "Repositorio: $REPO"
echo "Región:      $LOCATION"
echo

# 1 -------------------------------------------------------------------------
# La identidad de GitHub no podrá registrar proveedores (no tiene permisos de
# suscripción), así que se registran aquí una sola vez.
echo "==> Registrando proveedores de recursos (puede tardar un par de minutos)"
for ns in Microsoft.Web Microsoft.KeyVault Microsoft.Storage Microsoft.Insights \
          Microsoft.OperationalInsights Microsoft.Consumption; do
  az provider register --namespace "$ns" --wait --output none
  echo "    $ns: $(az provider show --namespace "$ns" --query registrationState -o tsv)"
done

# 2 -------------------------------------------------------------------------
echo "==> Grupos de recursos"
az group create --name "$APP_RG" --location "$LOCATION" --output none
az group create --name "$STATE_RG" --location "$LOCATION" --output none

# 3 -------------------------------------------------------------------------
echo "==> Almacenamiento del estado de Terraform ($STATE_SA)"
az storage account create \
  --name "$STATE_SA" --resource-group "$STATE_RG" --location "$LOCATION" \
  --sku Standard_LRS --min-tls-version TLS1_2 --allow-blob-public-access false \
  --output none
# container-rm usa el plano de control: no necesita permisos de datos ni espera propagación.
az storage container-rm create \
  --storage-account "$STATE_SA" --resource-group "$STATE_RG" --name tfstate --output none

# 4 -------------------------------------------------------------------------
echo "==> Identidad de GitHub ($IDENTITY_NAME)"
APP_ID="$(az ad app list --display-name "$IDENTITY_NAME" --query '[0].appId' -o tsv)"
if [ -z "$APP_ID" ]; then
  APP_ID="$(az ad app create --display-name "$IDENTITY_NAME" --query appId -o tsv)"
fi
APP_OBJECT_ID="$(az ad app show --id "$APP_ID" --query id -o tsv)"
SP_OBJECT_ID="$(az ad sp list --filter "appId eq '$APP_ID'" --query '[0].id' -o tsv)"
if [ -z "$SP_OBJECT_ID" ]; then
  SP_OBJECT_ID="$(az ad sp create --id "$APP_ID" --query id -o tsv)"
fi

ensure_credential() { # nombre, subject
  local name="$1" subject="$2" file
  if [ -n "$(az ad app federated-credential list --id "$APP_OBJECT_ID" \
        --query "[?name=='$name'].name" -o tsv)" ]; then
    echo "    credencial $name: ya existe"
    return
  fi
  file="$(mktemp)"
  cat > "$file" <<EOF
{
  "name": "$name",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "$subject",
  "audiences": ["api://AzureADTokenExchange"]
}
EOF
  az ad app federated-credential create --id "$APP_OBJECT_ID" --parameters "@$file" --output none
  rm -f "$file"
  echo "    credencial $name: creada ($subject)"
}

# Confianza: solo ESTE repositorio, y solo en estos contextos.
ensure_credential github-main        "repo:${REPO}:ref:refs/heads/main"
ensure_credential github-pr          "repo:${REPO}:pull_request"
ensure_credential github-env-prod    "repo:${REPO}:environment:prod"

ensure_role() { # rol, ámbito
  local role="$1" scope="$2"
  if [ "$(az role assignment list --assignee "$SP_OBJECT_ID" --role "$role" --scope "$scope" \
        --query 'length(@)' -o tsv)" != "0" ]; then
    echo "    rol $role: ya asignado"
    return
  fi
  az role assignment create --assignee-object-id "$SP_OBJECT_ID" \
    --assignee-principal-type ServicePrincipal --role "$role" --scope "$scope" --output none
  echo "    rol $role: asignado"
}

APP_RG_SCOPE="/subscriptions/${SUB_ID}/resourceGroups/${APP_RG}"
STATE_SA_SCOPE="/subscriptions/${SUB_ID}/resourceGroups/${STATE_RG}/providers/Microsoft.Storage/storageAccounts/${STATE_SA}"

echo "==> Roles (mínimo privilegio)"
ensure_role "Contributor"                   "$APP_RG_SCOPE"   # crear recursos en estudio-rg
ensure_role "User Access Administrator"     "$APP_RG_SCOPE"   # Terraform asigna roles a la Function
ensure_role "Storage Blob Data Contributor" "$STATE_SA_SCOPE" # leer/escribir el estado
ensure_role "Reader"                        "/subscriptions/${SUB_ID}" # solo lectura: recuperar Key Vault borrado

ADMIN_OBJECT_ID="$(az ad signed-in-user show --query id -o tsv 2>/dev/null || true)"

cat <<EOF

============================================================================
Listo. Crea estas VARIABLES en GitHub (no Secrets; con OIDC no hay secretos):
  Settings > Secrets and variables > Actions > pestaña "Variables" > New repository variable

  AZURE_CLIENT_ID        $APP_ID
  AZURE_TENANT_ID        $TENANT_ID
  AZURE_SUBSCRIPTION_ID  $SUB_ID
  TFSTATE_RG             $STATE_RG
  TFSTATE_SA             $STATE_SA
  APP_RG                 $APP_RG
  OWNER_TELEGRAM_ID      <tu id de @userinfobot>
  ADMIN_OBJECT_ID        ${ADMIN_OBJECT_ID:-<az ad signed-in-user show --query id -o tsv>}
  ALERT_EMAIL            <opcional: correo para avisos de presupuesto>

Después, en Settings > Environments, crea un entorno llamado "prod" y marca
"Required reviewers" con tu usuario: así Deploy y Destroy esperan tu aprobación.
============================================================================
EOF
