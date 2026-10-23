data "azurerm_client_config" "current" {}

# El grupo de recursos lo crea el bootstrap: así la identidad de GitHub puede tener
# permisos solo sobre él y no sobre toda la suscripción.
data "azurerm_resource_group" "main" {
  name = var.resource_group_name
}

locals {
  # Sufijo estable derivado de la suscripción: si destruyes y recreas, los nombres
  # (y por tanto la URL del webhook) no cambian.
  suffix = substr(sha1(data.azurerm_client_config.current.subscription_id), 0, 6)

  location = data.azurerm_resource_group.main.location
  rg_name  = data.azurerm_resource_group.main.name

    # El plan y la Function pueden vivir en otra región si la cuota es 0 en la del grupo.
  function_location = var.function_location != "" ? var.function_location : local.location

  names = {
    key_vault = "kv-${var.project}-${local.suffix}"
    storage   = "st${var.project}${local.suffix}"
    plan      = "asp-${var.project}-${local.suffix}"
    function  = "func-${var.project}-${local.suffix}"
    workspace = "log-${var.project}-${local.suffix}"
    insights  = "appi-${var.project}-${local.suffix}"
  }

  tags = merge(
    {
      proyecto       = "bot-estudio"
      gestionado-por = "terraform"
    },
    var.tags,
  )
}

# ---------------------------------------------------------------- almacenamiento
resource "azurerm_storage_account" "main" {
  name                            = local.names.storage
  resource_group_name             = local.rg_name
  location                        = local.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  tags                            = local.tags
}

# Tabla donde el bot guarda racha y progreso.
resource "azurerm_storage_table" "study" {
  name                 = "estudio"
  storage_account_name = azurerm_storage_account.main.name
}

# -------------------------------------------------------------------- key vault
# Terraform crea el vault pero NO el valor de los secretos: así el token del bot
# nunca entra en el estado. Lo guarda scripts/configure-bot.sh.
resource "azurerm_key_vault" "main" {
  name                       = local.names.key_vault
  resource_group_name        = local.rg_name
  location                   = local.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = 7
  purge_protection_enabled   = false
  tags                       = local.tags
}

# Tú (opcional): puedes guardar y rotar secretos.
resource "azurerm_role_assignment" "admin_secrets" {
  count                = var.admin_object_id == "" ? 0 : 1
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = var.admin_object_id
}

# ---------------------------------------------------------------- observabilidad
resource "azurerm_log_analytics_workspace" "main" {
  name                = local.names.workspace
  resource_group_name = local.rg_name
  location            = local.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 0.5 # tope diario: evita sorpresas de costo
  tags                = local.tags
}

resource "azurerm_application_insights" "main" {
  name                = local.names.insights
  resource_group_name = local.rg_name
  location            = local.location
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
  tags                = local.tags
}

# --------------------------------------------------------------------- función
resource "azurerm_service_plan" "bot" {
  name                = local.names.plan
  resource_group_name = local.rg_name
  location            = local.function_location
  os_type             = "Linux"
  sku_name            = var.function_plan_sku
  tags                = local.tags
}

resource "azurerm_linux_function_app" "bot" {
  name                = local.names.function
  resource_group_name = local.rg_name
  location            = local.function_location
  service_plan_id     = azurerm_service_plan.bot.id

  # El plan de consumo (Y1) exige acceso por clave para el contenido de la app.
  storage_account_name       = azurerm_storage_account.main.name
  storage_account_access_key = azurerm_storage_account.main.primary_access_key

  https_only                  = true
  functions_extension_version = "~4"

  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on                              = var.function_plan_sku != "Y1"
    application_insights_connection_string = azurerm_application_insights.main.connection_string
    ftps_state                             = "Disabled"
    minimum_tls_version                    = "1.2"

    application_stack {
      python_version = "3.11"
    }
  }

  app_settings = {
    # Referencias a Key Vault: el valor se resuelve en tiempo de ejecución con la
    # identidad administrada. Si el secreto aún no existe, /api/health lo indica.
    TELEGRAM_BOT_TOKEN      = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=telegram-bot-token)"
    TELEGRAM_WEBHOOK_SECRET = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=telegram-webhook-secret)"

    OWNER_TELEGRAM_ID = var.owner_telegram_id
    TABLES_ENDPOINT   = azurerm_storage_account.main.primary_table_endpoint
    STUDY_TIMEZONE    = "America/Bogota"
    DAILY_SCHEDULE    = var.daily_schedule

    # `az functionapp deployment source config-zip --build-remote` los activa por su
    # cuenta; declararlos aquí evita que Terraform vea un cambio en cada plan.
    ENABLE_ORYX_BUILD              = "true"
    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
  }

  tags = local.tags

  lifecycle {
    # El despliegue de código gestiona este ajuste.
    ignore_changes = [app_settings["WEBSITE_RUN_FROM_PACKAGE"]]
  }
}

# La función lee secretos y escribe en la tabla con su identidad, sin contraseñas.
resource "azurerm_role_assignment" "function_reads_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_linux_function_app.bot.identity[0].principal_id
}

resource "azurerm_role_assignment" "function_uses_tables" {
  scope                = azurerm_storage_account.main.id
  role_definition_name = "Storage Table Data Contributor"
  principal_id         = azurerm_linux_function_app.bot.identity[0].principal_id
}

# ------------------------------------------------------------------ presupuesto
resource "azurerm_consumption_budget_resource_group" "main" {
  count             = var.alert_email == "" ? 0 : 1
  name              = "budget-${var.project}"
  resource_group_id = data.azurerm_resource_group.main.id
  amount            = var.monthly_budget_usd
  time_grain        = "Monthly"

  time_period {
    start_date = "${formatdate("YYYY-MM", plantimestamp())}-01T00:00:00Z"
  }

  notification {
    enabled        = true
    threshold      = 80
    threshold_type = "Actual"
    operator       = "GreaterThan"
    contact_emails = [var.alert_email]
  }

  notification {
    enabled        = true
    threshold      = 100
    threshold_type = "Forecasted"
    operator       = "GreaterThan"
    contact_emails = [var.alert_email]
  }

  lifecycle {
    # La fecha de inicio solo importa al crearlo.
    ignore_changes = [time_period]
  }
}
