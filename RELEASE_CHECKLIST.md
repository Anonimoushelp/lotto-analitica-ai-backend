# Checklist de release

## Identificación

- [ ] Registrar commit SHA exacto desplegado.
- [ ] Confirmar CI exitoso para ese SHA.
- [ ] Registrar la versión/release anterior disponible para rollback.

## Antes del despliegue

- [ ] Migraciones Alembic verificadas con upgrade/downgrade/upgrade en CI.
- [ ] Compatibilidad aplicación-esquema revisada.
- [ ] Backup PostgreSQL disponible y restauración verificable según el checklist de producción.
- [ ] Si el cambio introduce datos personales: propósito, acceso, retención, eliminación/anonimización, logging y efecto en backups documentados.
- [ ] Runbook de observabilidad y respuesta ante abuso revisado: `docs/OBSERVABILITY_RUNBOOK.md`.

## Después del despliegue

- [ ] `/health` responde correctamente.
- [ ] Readiness de base de datos validada.
- [ ] Rutas críticas verificadas.
- [ ] Logs revisados sin exposición de secretos o datos personales innecesarios.
- [ ] Revisar 4xx/5xx/429, latencia y errores de PostgreSQL/Redis durante la ventana posterior al despliegue.

## Retención y privacidad

- [ ] Revisar anualmente usuarios inactivos y aplicar eliminación/anonimización cuando ya no exista una necesidad legítima de conservación.
- [ ] Confirmar que backups y registros de auditoría siguen una retención coherente con su finalidad.
- [ ] No almacenar contraseñas, tokens, hashes de contraseña ni payloads con PII en logs.

## Si el despliegue falla

- [ ] Identificar SHA estable anterior.
- [ ] Contener nuevos despliegues.
- [ ] Restaurar la versión de aplicación anterior sin downgrade automático del esquema.
- [ ] Repetir health/readiness/rutas críticas.
- [ ] Registrar incidente y SHA restaurado.
