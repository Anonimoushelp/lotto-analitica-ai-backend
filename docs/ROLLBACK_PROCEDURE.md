# Procedimiento de rollback de despliegue

## Objetivo

Restaurar la aplicación a la última versión conocida como estable sin ejecutar un rollback independiente del esquema de base de datos.

## Requisitos previos

- Cada despliegue de producción debe corresponder a un commit SHA verificable de `main`.
- Conservar disponible el release/imagen inmediatamente anterior al despliegue.
- Verificar que el CI del SHA objetivo terminó en `success` antes de seleccionarlo como versión de recuperación.
- Confirmar compatibilidad entre la versión de aplicación objetivo y el esquema actual de PostgreSQL.

## Contención ante fallo

1. Identificar el SHA de producción actualmente desplegado y el último SHA estable.
2. Detener nuevos despliegues automáticos mientras se diagnostica el incidente.
3. Si la aplicación presenta errores de ejecución, enrutar el servicio a la versión estable anterior conservando el mismo esquema de datos.
4. No ejecutar `alembic downgrade` como parte del rollback de aplicación salvo que exista un procedimiento específico, validado y compatible con la versión objetivo.
5. Verificar `/health`, conectividad con PostgreSQL y las rutas críticas después del cambio.
6. Revisar logs y confirmar que desapareció la condición de fallo antes de reanudar despliegues.

## Validación posterior

- Registrar SHA anterior, SHA restaurado, motivo, hora y resultado.
- Confirmar que el SHA restaurado corresponde a un commit existente y a un CI exitoso.
- Ejecutar las comprobaciones de producción definidas en `DEPLOYMENT_PRODUCTION_CHECKLIST.md`.
- Abrir una corrección posterior antes de volver a desplegar la versión que provocó el incidente.

## Regla de seguridad de datos

El rollback de la aplicación y el rollback del esquema son operaciones independientes. Nunca se debe revertir el esquema por reflejo ante un fallo de aplicación. Toda migración destructiva requiere una estrategia explícita de compatibilidad y recuperación de datos.

## Evidencia de versionado

GitHub Releases se utiliza como mecanismo recomendado para conservar una referencia de versión estable y facilitar la identificación del artefacto de recuperación. Mientras no exista un release publicado, el SHA exacto del commit y el artefacto de despliegue equivalente deben conservarse como referencia operativa.
