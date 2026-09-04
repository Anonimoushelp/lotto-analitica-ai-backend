# Runbook de observabilidad, abuso y respuesta operativa

## Objetivo

Establecer una guía operativa para detectar degradación, abuso sostenido y fallos de dependencias sin registrar secretos ni datos personales innecesarios.

## Señales mínimas a revisar

- Respuestas HTTP 5xx y aumentos sostenidos de 4xx/429.
- Latencia elevada en `/api/v1/auth/*`, `/api/v1/draws` y `/api/v1/lotteries`.
- Incrementos de rechazos por rate limit en autenticación.
- Errores de conexión o timeout de PostgreSQL y Redis.
- Reinicios o despliegues repetidos del servicio.
- `/health` y las rutas críticas después de cada despliegue.

## Indicadores de abuso

Investigar cuando coincidan una o más señales:

- Incremento anómalo de 429 desde una misma fuente.
- Incremento de 401/403 concentrado en una misma ventana.
- Picos sostenidos de solicitudes sobre endpoints de lectura o mutación.
- Aumento simultáneo de latencia y agotamiento del pool de conexiones.
- Repetición de errores 5xx bajo tráfico elevado.

La IP y los identificadores de usuario solo deben utilizarse para investigación operativa cuando sean necesarios y conforme a la política de retención y privacidad.

## Respuesta escalonada

1. Confirmar si el patrón es real y si afecta disponibilidad o integridad.
2. Revisar logs de aplicación, Redis, PostgreSQL y plataforma de despliegue.
3. Identificar endpoint, ventana temporal y tipo de respuesta predominante.
4. Si existe abuso de autenticación, verificar el rate limiter y sus errores de dependencia.
5. Si existe agotamiento de recursos, contener tráfico abusivo y revisar límites de pool/timeouts antes de aumentar capacidad.
6. Si existe degradación de producción, aplicar el procedimiento de rollback documentado y validar health/readiness/rutas críticas.
7. Registrar incidente, impacto, ventana temporal, acciones y SHA afectado.

## Criterios de escalamiento

Escalar como incidente cuando exista indisponibilidad, degradación sostenida, evidencia de evasión del rate limit, errores repetidos de dependencias o riesgo para integridad de datos.

## Privacidad de logs

No registrar contraseñas, tokens, hashes de contraseña, correos electrónicos ni payloads completos. Los eventos de auditoría deben conservar únicamente los identificadores operativos estrictamente necesarios.

## Validación posterior

Después de contener el evento o desplegar una corrección, comprobar `/health`, las rutas críticas, ausencia de errores 5xx nuevos y comportamiento normal del rate limiting antes de cerrar el incidente.
