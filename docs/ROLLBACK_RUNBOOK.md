# Runbook de rollback

1. Registrar el SHA actualmente desplegado.
2. Seleccionar únicamente un SHA estable cuyo CI esté completado con `success`.
3. Pausar nuevos despliegues.
4. Restaurar el artefacto de aplicación asociado al SHA estable anterior.
5. Mantener el esquema PostgreSQL actual; no ejecutar `alembic downgrade` automáticamente.
6. Validar `/health`, readiness de PostgreSQL y rutas críticas.
7. Revisar logs y registrar SHA restaurado, causa y resultado.
