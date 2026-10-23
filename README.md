# Bot de estudio en Azure (Terraform + Functions + agente)

Un bot de Telegram que te manda cada día una pregunta de repaso (Terraform, Azure, Docker, Kubernetes, GitHub Actions, desarrollo), lleva tu **racha** y repite antes las que fallas (repetición espaciada). Está pensado para aprender **desarrollo** (escribir y probar el bot) y **nube** (hospedarlo, protegerlo, observarlo) con Terraform como única fuente de verdad.

> Estado: **fases 1 a 3** hechas (bot, Terraform, despliegue). Las fases 4 a 6 (alertas, agente, Docker) están en [Hoja de ruta](#hoja-de-ruta).

## Arquitectura

```
Telegram ──webhook──▶ Azure Function (Python 3.11, plan de consumo)
                         │  /api/telegram  (valida el secreto del webhook)
                         │  /api/health    (diagnóstico sin revelar secretos)
                         │  timer diario   (pregunta automática)
                         ├──▶ Key Vault        token y secreto del webhook (referencias, sin claves en el código)
                         ├──▶ Table Storage    racha y progreso (identidad administrada, sin claves)
                         └──▶ Application Insights + Log Analytics   logs y métricas
```

Terraform crea todo dentro de un grupo de recursos: Storage + tabla, Key Vault, Log Analytics, Application Insights, plan y Function App, dos asignaciones de rol para la Function y, si pones un correo, un presupuesto mensual.

## Decisiones de diseño (y por qué)

| Decisión | Motivo |
| --- | --- |
| **Sin Docker en esta fase** | Functions con código Python es lo más simple y casi gratis. Docker se estudia en la fase 6, con un caso real. |
| **Webhook, no polling** | Telegram llama a tu función cuando hay mensaje; no hay proceso encendido esperando. |
| **El token nunca entra en Terraform** | Terraform crea el vault; el valor lo guarda `configure-bot.sh`. Así no queda en el estado. |
| **OIDC en vez de contraseña** | GitHub se autentica con un token de corta duración. **Este repo no tiene ningún Secret de GitHub.** |
| **El grupo de recursos lo crea el bootstrap** | La identidad de GitHub tiene permisos solo sobre ese grupo, no sobre la suscripción (el punto débil del proyecto anterior). |
| **Aprobación humana para aplicar** | Deploy y Destroy usan el entorno `prod` con revisores obligatorios. |
| **Solo responde a tu id de Telegram** | Cualquier otro usuario es ignorado y solo se registra su id. |
| **Sin destroy nocturno** | Aquí el costo en reposo son centavos y destruir borra los secretos del vault. El presupuesto con alerta es la red de seguridad. |

## Puesta en marcha

Necesitas: una suscripción de Azure, una cuenta de GitHub y Telegram.

**1. Crea el bot y obtén tu id**
- En Telegram habla con `@BotFather`, ejecuta `/newbot` y guarda el token (no lo pegues en ningún chat ni archivo).
- Habla con `@userinfobot` para ver tu id numérico.

**2. Sube este repositorio a GitHub** (puede ser privado) y abre Azure Cloud Shell (Bash). Clona el repo allí.

**3. Ejecuta el bootstrap una sola vez**
```bash
bash scripts/bootstrap-github.sh <tu-usuario>/<tu-repo>
```
Imprime las **Variables** que debes crear en GitHub (`Settings > Secrets and variables > Actions > Variables`). Añade `OWNER_TELEGRAM_ID` con tu id.

**4. Crea el entorno `prod`** en `Settings > Environments`, con *Required reviewers* = tú.

**5. Despliega**: pestaña *Actions* → **Deploy** → *Run workflow* (desde `main`). Revisa el plan en el resumen, aprueba, y espera a que termine. El resumen final muestra el comando del paso siguiente.

**6. Termina la configuración** en Cloud Shell, con el comando del resumen:
```bash
bash scripts/configure-bot.sh <grupo> <key-vault> <function-app>
```
Pide el token oculto, lo guarda en Key Vault, reinicia la app y registra el webhook. Escríbele `/start` a tu bot.

## Uso

| Comando | Qué hace |
| --- | --- |
| `/pregunta` | Una pregunta de repaso; botón para ver la respuesta y marcar si la sabías |
| `/racha` | Racha de días, preguntas vistas, dominadas y porcentaje de aciertos |
| `/ayuda` | Ayuda |

Cada día a las 09:00 (Bogotá) llega una pregunta automática, salvo que ya hayas estudiado ese día. Cambia la hora con la variable de Terraform `daily_schedule` (NCRONTAB, en UTC). Las preguntas están en `app/questions.json`: añade las tuyas.

## Desarrollo local

```bash
cd app
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q          # 50 pruebas, sin Azure ni Telegram
```
La lógica (`study.py`, `bot.py`) está separada de Azure y de Telegram con inyección de dependencias, por eso se prueba con objetos falsos. Para ejecutar la función completa en local necesitas Azure Functions Core Tools y Azurite (copia `local.settings.json.example`).

Terraform en local:
```bash
cd terraform
az login && export ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
cp terraform.tfvars.example terraform.tfvars   # edita tus valores
terraform init && terraform validate && terraform plan
```
Haz commit de `terraform/.terraform.lock.hcl` la primera vez que se genere.

## Costos

Con el plan de consumo, el costo en reposo es de **centavos al mes** (Storage, Key Vault, Application Insights con tope diario de 0.5 GB). Pon `ALERT_EMAIL` para recibir avisos al 80 % y al 100 % previsto de `monthly_budget_usd` (5 por defecto). Para borrar todo: flujo **Destroy** (escribe `destruir`). El grupo de recursos y el estado de Terraform se conservan.

## Problemas que probablemente verás

Salen de las lecciones del proyecto anterior; cada uno trae su pista de diagnóstico.

| Síntoma | Causa probable | Qué hacer |
| --- | --- | --- |
| `SkuNotAllowed` o cuota 0 al crear el plan | La suscripción no permite el plan de consumo en esa región (igual que la VM del AKS) | Cambia `LOCATION` en el bootstrap o prueba otra región; `plan` válido no garantiza `apply` |
| `check-config` dice `definido: NO` | La variable está en *Secrets* o falta | Créala en la pestaña **Variables** |
| `AADSTS70021` / `AADSTS700016` en `azure/login` | La credencial federada no coincide con el contexto del job | Ejecuta desde `main`, con el entorno `prod` en `apply`; revisa los `subject` que imprimió el bootstrap |
| `AuthorizationFailed` al crear proveedores | Falta registrar un proveedor | Vuelve a ejecutar el bootstrap |
| `/api/health` con `token_configured: false` | El secreto no existe aún o la Function no puede leerlo | Ejecuta `configure-bot.sh`; espera 1-2 minutos por la propagación de roles |
| Telegram no responde | Webhook sin registrar, o escribes desde otro usuario | `getWebhookInfo` muestra `last_error_message`; revisa `OWNER_TELEGRAM_ID` |
| Error `Forbidden` al guardar secretos | Tu usuario no tiene *Key Vault Secrets Officer* | Define `ADMIN_OBJECT_ID` y vuelve a desplegar |
| Error al recrear Key Vault tras un destroy | El vault está en borrado suave | Terraform lo recupera si la identidad puede leer la suscripción (rol *Reader* del bootstrap) |

## Seguridad: qué está hecho y qué falta

Hecho: OIDC sin contraseñas, permisos solo sobre un grupo de recursos, secretos en Key Vault con RBAC, identidad administrada para la Function, validación del secreto del webhook con comparación en tiempo constante, bot restringido a un usuario, tokens fuera de los logs (probado), aprobación manual para aplicar, `timeout` en toda llamada externa.

Por endurecer: *User Access Administrator* sin restricciones sobre el grupo (se puede limitar con *Role Based Access Control Administrator* y una condición); el plan de consumo exige acceso por clave a la cuenta de Storage de la app; el `apply` vuelve a planificar tras la aprobación (el plan aprobado y el aplicado pueden diferir si el código cambió entre medias); idempotencia de updates duplicados de Telegram (`update_id`).

## Hoja de ruta

| Fase | Qué | Notas |
| --- | --- | --- |
| 4 | Alertas (excepciones, errores 5xx, función sin ejecutarse) y comandos `/estado` y `/costo` | Terraform: `azurerm_monitor_scheduled_query_rules_alert_v2` + grupo de acción |
| 5 | **Agente**: lee la alerta y los logs, propone el arreglo como pull request | Reglas en [AGENTS.md](AGENTS.md); nunca ejecuta apply |
| 6 | Migrar a Container Apps con Docker (opcional) | Imagen construida en el pipeline; Terraform solo recibe la etiqueta |

## Estructura

```
app/         function_app.py, bot.py, study.py, storage.py, telegram.py, webhook.py, questions.json, tests/
terraform/   provider.tf, variables.tf, main.tf, outputs.tf
scripts/     bootstrap-github.sh, configure-bot.sh, write-backend.sh, check-config.sh
.github/     workflows/ (ci, plan, deploy, destroy)
AGENTS.md    reglas del agente
```
