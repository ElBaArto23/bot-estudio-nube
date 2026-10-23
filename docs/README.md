# Evidencias: bot-estudio-nube

Despliegue en Azure con Terraform y GitHub Actions (OIDC), 23/10/2026.
Recursos: Function App (Python 3.11, plan Y1, Central US), Key Vault, Storage con tabla, Log Analytics y Application Insights.

| Archivo | Qué demuestra |
| --- | --- |
| 01-plan-terraform.txt | Plan aprobado: 4 recursos por crear, 0 cambios, 0 destrucciones (plan Y1 en centralus) |
| 02-deploy-3-exitoso.png | Workflow Deploy #3: plan, apply (con aprobación del entorno prod) y code en verde |
| 03, 04-recursos-estudio-rg | Los 7 recursos creados en el grupo `estudio-rg` |
| 05-health-endpoint.png | `/api/health` responde `status: ok` con token, secreto del webhook y propietario configurados |
| 06-telegram-conversacion.jpg | El bot responde a `/start`, `/pregunta` y `/racha` |
| 07, 08, 09 | Application Insights, tabla `requests`: peticiones `telegram_webhook` y `health` con código 200 |
| 10 | Application Insights, tabla `traces`: registros de la Function |
| 11, 12, 13 | Incidente: el bot no respondía aunque `requests` mostraba 200. Los `traces` revelaron `TelegramError: sendMessage: HTTP 404`. Causa: la Function conservaba en caché el valor antiguo de la referencia a Key Vault. |
| 14-destroy-grupo-vacio.png | Tras el Destroy, `estudio-rg` queda con 0 recursos. El workflow destruyó lo que Terraform administraba; quedaron el workspace de Log Analytics (borrado suave) y el grupo de acciones automático de Application Insights, que se borraron a mano. Se corrigió en `provider.tf` y `destroy.yml`. |
| 15-destroy-workflow-verde.png | Workflow Destroy #1 en verde tras re-ejecutarlo (intento #2, commit `b064ffc`, anterior al arreglo), con el grupo ya vacío por la limpieza manual. El primer intento destruyó lo administrado por Terraform y falló solo en la verificación final. El arreglo está pendiente de probar en el próximo ciclo. |

## Lecciones del incidente
- Un 200 en `requests` solo prueba que la Function respondió a Telegram; el handler devuelve 200 aunque falle por dentro para evitar reintentos. Hay que mirar `traces` (severidad 3).
- Reiniciar la app no actualiza las referencias a Key Vault; cambiar un ajuste de la app sí.

- Application Insights crea un grupo de acciones que Terraform no conoce, y Log Analytics conserva el workspace 14 días tras borrarlo. Ambos casos quedaron resueltos en el código.
