# Guía de Uso - Agentes Fase 1

## Propósito
Esta guía describe cómo usar los agentes definidos para la Fase 1 de integración en Lotto Analítica AI. Estos agentes operan **únicamente en sesión OpenCode** y bajo estrictos controles.

## Agentes disponibles
| Agente | Cuándo usarlo |
|---|---|
| **coordinador** | Para planificar cualquier tarea, verificar alcance y obtener gates de aprobación |
| **calidad-datos** | Para validar integridad de draws, catálogo, idempotencia sin modificar nada |
| **analista-estadistico** | Para analizar datos históricos reales, con métricas verificables y sin garantías |
| **pruebas-revision** | Para revisar diffs, ejecutar tests seguros (sin integración/BD/migraciones) |

## Flujo recomendado
1. **Iniciar con Coordinador** - Definir objetivo, verificar rama/estado, obtener plan
2. **Validar con especialistas** - Usar `calidad-datos` o `analista-estadistico` según necesidad
3. **Revisar antes de cambios** - Usar `pruebas-revision` para evaluar cualquier propuesta
4. **Solicitar autorización** - Si se requiere escritura, detener y pedir autorización explícita

## Reglas de uso
- **Solo en sesión:** No crear tareas recurrentes
- **Rama de trabajo:** Siempre verificar estar en `feature/agents-phase1-integration` o rama aprobada
- **Sin escrituras automáticas:** Cualquier modificación requiere autorización explícita
- **Sin secretos:** Nunca compartir credenciales o valores de .env
- **Tests seguros:** Solo ejecutar tests marcados `not integration`, sin migraciones/BD

## Comandos seguros para validación
```bash
# Verificar estado
git branch --show-current
git status --short

# Linting
ruff check app tests

# Sintaxis
python -m compileall -q app tests

# Tests seguros (sin integración)
pytest -q -m "not integration"
```

## Documentación relacionada
- `AGENTS.md` - Directrices globales
- `docs/agents/CONTROLES.md` - Controles y condiciones de parada
- `.opencode/agents/*.md` - Configuración detallada por agente
