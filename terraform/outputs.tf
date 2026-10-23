output "resource_group_name" {
  description = "Grupo de recursos donde vive todo."
  value       = local.rg_name
}

output "function_app_name" {
  description = "Nombre de la Function App (destino del despliegue de código)."
  value       = azurerm_linux_function_app.bot.name
}

output "function_app_hostname" {
  description = "Host público de la Function App."
  value       = azurerm_linux_function_app.bot.default_hostname
}

output "key_vault_name" {
  description = "Key Vault donde se guardan el token y el secreto del webhook."
  value       = azurerm_key_vault.main.name
}

output "webhook_url" {
  description = "URL que se registra en Telegram."
  value       = "https://${azurerm_linux_function_app.bot.default_hostname}/api/telegram"
}

output "configure_command" {
  description = "Comando para terminar la configuración (token y webhook)."
  value       = "bash scripts/configure-bot.sh ${local.rg_name} ${azurerm_key_vault.main.name} ${azurerm_linux_function_app.bot.name}"
}
