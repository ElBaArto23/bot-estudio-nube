terraform {
  required_version = ">= 1.6"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  # Sin bloque backend a propósito: en local el estado es un archivo; en GitHub
  # Actions, scripts/write-backend.sh crea backend_ci.tf con el estado remoto.
}

provider "azurerm" {
  # Credenciales: variables ARM_* o la sesión de `az login` / azure/login (OIDC).
  # La suscripción llega por ARM_SUBSCRIPTION_ID.

  # La identidad de GitHub solo tiene permisos sobre un grupo de recursos, así que
  # no puede registrar proveedores de recursos: lo hace scripts/bootstrap-github.sh.
  resource_provider_registrations = "none"

  features {
    key_vault {
      # Un destroy deja el vault en "borrado suave" (7 días) en vez de purgarlo,
      # porque purgar exige permisos a nivel de suscripción. Al recrearlo con el
      # mismo nombre, Terraform lo recupera junto con sus secretos.
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }

    log_analytics_workspace {
      # Sin esto, Azure conserva el workspace 14 días en borrado suave: sigue
      # apareciendo en el grupo y bloquea su nombre si vuelves a desplegar.
      permanently_delete_on_destroy = true
    }
  }
}
