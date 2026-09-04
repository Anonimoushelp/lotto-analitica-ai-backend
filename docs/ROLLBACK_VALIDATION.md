# Validación de rollback

Esta referencia exige conservar el SHA exacto de la versión estable anterior y verificar su CI antes de seleccionarla para recuperación. El rollback de aplicación no implica un downgrade automático de Alembic. Después de restaurar la versión, se deben repetir health, readiness y rutas críticas.
