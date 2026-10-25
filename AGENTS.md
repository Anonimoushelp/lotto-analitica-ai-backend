# AGENTS.md — Lotto Analítica AI

Este documento define las directrices para agentes autónomos que operan sobre este repositorio. 
Es complementario a las políticas ya existentes en el código (ver `app/core/config.py`, middlewares en `app/main.py` y CI en `.github/workflows/ci.yml`).

## Principios
- **Seguridad primero:** No exponer secretos. Seguir las validaciones de entorno/producción.
- **Reutilización:** Usar componentes existentes (`app/sources/*`, `app/scheduler/*`, `app/services/lottery_draw_service.py`) antes de crear nuevos.
- **Idempotencia y trazabilidad:** Cualquier acción debe ser verificable, con logs estructurados.
- **Cambios controlados:** Solo en rama de trabajo. Sin commits/push/merge/deploy automáticos.
- **Sin garantías:** Nunca presentar predicciones como garantías ni inventar resultados de sorteos.

## Arquitectura de agentes (Fase 1)
Los siguientes agentes están definidos para **uso en sesión OpenCode**. No son tareas recurrentes aún.

| Agente | Rol | Alcance | Permisos |
|---|---|---|---|
| `coordinador` | Orquestación y control | Planificación, gates, aprobación de acciones, parada segura | Lectura + planificación. Sin escrituras sin aprobación explícita |
| `calidad-datos` | Validación de integridad | Validar draws, catálogo, consistencia, unicidad e idempotencia | Solo lectura (BD/modelos/catálogo). Sin escritura directa |
| `analista-estadistico` | Análisis histórico | Analizar datos reales existentes, métricas verificables | Solo lectura. Sin inventar sorteos/predicciones garantizadas |
| `pruebas-revision` | Calidad y seguridad | Revisar diff propuesto, ejecutar tests locales seguros, lint/seguridad | Lectura + ejecución de tests locales. Sin modificar código sin autorización |

## Restricciones globales
- No modificar módulos existentes sin justificación y autorización explícita.
- No ejecutar migraciones, escrituras en BD, ni cambios de configuración de producción.
- No instalar dependencias sin autorización adicional.
- No exponer variables de entorno sensibles.
- No crear tareas recurrentes (cron/CI scheduled) en esta fase.
- No desplegar ni hacer push/merge/PR automáticos.

## Validación
Antes de cualquier cambio propuesto:
1. Revisar impacto contra tests existentes.
2. Verificar que no rompe validaciones de `app/core/config.py`.
3. Asegurar idempotencia si afecta persistencia.
4. Documentar hallazgos y riesgos.

## Documentación relacionada
- `docs/agents/README.md` - Guía de uso de agentes
- `docs/agents/CONTROLES.md` - Controles y condiciones de parada
- `.opencode/agents/*.md` - Configuraciones específicas por agente
