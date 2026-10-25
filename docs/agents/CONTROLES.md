# Controles y Condiciones de Parada - Fase 1

## Controles obligatorios
| Control | Descripción | Acción |
|---|---|---|
| **Verificación de rama** | Debe estar en rama de trabajo (no `main` para cambios) | Verificar antes de cualquier propuesta de escritura |
| **Estado git limpio o controlado** | Revisar cambios sin guardar | Preservar cambios existentes, no sobrescribir |
| **Alcance acotado** | Solo acciones autorizadas en Fase 1 | Detener si excede alcance |
| **Sin secretos** | Nunca mostrar valores de credenciales/env | Redactar cualquier dato sensible |
| **Sin operaciones destructivas** | No migraciones, no escritura BD, no deploy | Bloquear automáticamente |

## Condiciones de parada (HARD STOPS)
Detener inmediatamente y solicitar autorización específica si:
- [ ] Se intenta modificar archivos sin autorización explícita
- [ ] Se intenta instalar dependencias (`pip install`, `npm install`, etc.)
- [ ] Se intenta ejecutar `alembic upgrade/downgrade/stamp`
- [ ] Se intenta escribir en base de datos
- [ ] Se intenta hacer `git commit`, `git push`, `git merge`, crear PR
- [ ] Se intenta desplegar a Railway/Neon/Vercel
- [ ] Se intenta crear tareas recurrentes (cron, GitHub scheduled workflows)
- [ ] Se intenta habilitar publicación automática u operaciones financieras
- [ ] Se detectan secretos/credenciales en salida
- [ ] Se intenta conceder permisos globales irrestrictos
- [ ] Se propone cambiar lógica de negocio o algoritmos estadísticos
- [ ] Se propone reescribir/eliminar módulos existentes
- [ ] Se intenta ejecutar tests marcados como `integration`

## Validación post-cambios
Después de cualquier cambio (solo si autorizado):
1. Listar archivos creados/modificados
2. Explicar función de cada agente
3. Ejecutar comprobaciones locales pertinentes
4. Reportar pruebas aprobadas/fallidas
5. Verificar cambios limitados a rama de trabajo
6. Listar acciones pendientes que requieran autorización

## Permisos mínimos por agente
| Agente | Lectura | Escritura | Ejecución | Notas |
|---|---|---|---|---|
| coordinador | Completa | Ninguna | Solo inspección | Gatekeeper |
| calidad-datos | Código/modelos/catálogos | Ninguna | Ninguna | Solo análisis |
| analista-estadistico | Código/servicios stats | Ninguna | Ninguna | Sin predicciones garantizadas |
| pruebas-revision | Completa | Ninguna | Tests seguros/lint/compileall | Sin integración/migraciones |

## Registro de acciones
Todo agente debe documentar: acción propuesta, justificación, alcance, riesgos, autorización requerida (sí/no).
