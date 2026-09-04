# Checklist de release

## Identificación

- [ ] Registrar commit SHA exacto desplegado.
- [ ] Confirmar CI exitoso para ese SHA.
- [ ] Registrar la versión/release anterior disponible para rollback.

## Antes del despliegue

- [ ] Migraciones Alembic verificadas con upgrade/downgrade/upgrade en CI.
- [ ] Compatibilidad aplicación-esquema revisada.
- [ ] Backup PostgreSQL disponible y restauración verificable según el checklist de producción.

## Después del despliegue

- [ ] `/health` responde correctamente.
- [ ] Readiness de base de datos validada.
- [ ] Rutas críticas verificadas.
- [ ] Logs revisados sin exposición de secretos.

## Si el despliegue falla

- [ ] Identificar SHA estable anterior.
- [ ] Contener nuevos despliegues.
- [ ] Restaurar la versión de aplicación anterior sin downgrade automático del esquema.
- [ ] Repetir health/readiness/rutas críticas.
- [ ] Registrar incidente y SHA restaurado.
