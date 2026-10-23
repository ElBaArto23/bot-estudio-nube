variable "project" {
  description = "Nombre corto del proyecto. Entra en los nombres de los recursos."
  type        = string
  default     = "botestudio"

  validation {
    condition     = can(regex("^[a-z0-9]{3,12}$", var.project))
    error_message = "project debe tener entre 3 y 12 caracteres: minúsculas y números (los nombres de Storage y Key Vault son estrictos)."
  }
}

variable "resource_group_name" {
  description = "Grupo de recursos que ya existe (lo crea scripts/bootstrap-github.sh). Terraform administra lo que hay dentro, no el grupo."
  type        = string
  default     = "estudio-rg"
}

variable "owner_telegram_id" {
  description = "Tu id numérico de Telegram (pregúntaselo a @userinfobot). Solo este usuario puede usar el bot."
  type        = string

  validation {
    condition     = can(regex("^[0-9]+$", var.owner_telegram_id))
    error_message = "owner_telegram_id debe ser un número, por ejemplo 123456789."
  }
}

variable "admin_object_id" {
  description = "Object id de tu usuario en Entra ID. Si lo pones, recibes permiso para guardar secretos en Key Vault (lo imprime bootstrap-github.sh)."
  type        = string
  default     = ""
}

variable "alert_email" {
  description = "Correo para avisos de presupuesto. Vacío = no se crea presupuesto."
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  description = "Presupuesto mensual del grupo de recursos, en dólares."
  type        = number
  default     = 5
}

variable "function_plan_sku" {
  description = "SKU del plan de la Function App. Y1 = consumo (casi gratis en reposo)."
  type        = string
  default     = "Y1"
}

variable "function_location" {
  description = "Región del plan y de la Function App. Vacío = la del grupo de recursos. Cámbiala si la suscripción no tiene cuota del plan en esa región."
  type        = string
  default     = "centralus"
}

variable "daily_schedule" {
  description = "Hora de la pregunta diaria en formato NCRONTAB (seg min hora día mes díaSemana), en UTC. Por defecto 14:00 UTC = 09:00 en Bogotá."
  type        = string
  default     = "0 0 14 * * *"
}

variable "tags" {
  description = "Etiquetas adicionales para todos los recursos."
  type        = map(string)
  default     = {}
}
