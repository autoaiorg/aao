# AAO Control Center — Centro de Mando del CEO (F1-F2)

Aplicación web moderna para la supervisión global, cartera de proyectos, ciclo de vida de tareas y estado observable de la organización digital AAO.

Desarrollada por **Antigravity** (`aao-impl-ag`) conforme al mandato técnico `AAO-FE-ARCH-2026-10-25`.

---

## Características Implementadas (Fases F1 + F2)

1. **Shell y Navegación Accesible (WCAG 2.2 AA):**
   - Cabecera con selector de proyecto, conmutador de entorno `LIVE / DEMO`, estado de identidad y refresco manual.
   - Navegación lateral estructurada: Resumen, Proyectos, Tablero Kanban, Organización (F3), Decisiones, Alertas, Auditoría, Operaciones, Oficina Virtual (F4) y Configuración.
   - Compatibilidad completa con navegación por teclado y contraste adaptativo.

2. **Dashboard Ejecutivo del CEO:**
   - 4 tarjetas métricas: Cartera de proyectos, Total de tareas, Tareas en revisión y Salud de servicios.
   - Muestra explícitamente estados `unavailable` sin recurrir a ceros inventados cuando un contrato no está disponible.
   - Gráfico de progreso de trabajo por estados de ciclo de vida con alternativa tabular accesible.
   - Panel de cartera de proyectos activos con navegación directa.
   - Centro consultivo de decisiones y certificación de gobernanza.

3. **Cartera y Detalle de Proyectos:**
   - Búsqueda en tiempo real y filtrado por estado.
   - Detalle de proyecto con catálogo de capacidades (skills, scripts, libraries) y evaluaciones.
   - Invariante: las capacidades indican explícitamente `Ejecución autorizada: no`.

4. **Tablero Kanban con Seis Estados Canónicos:**
   - Preserva los 6 estados de AAO: `INBOX` (Entrada), `READY` (Preparado), `IN_PROGRESS` (En curso), `IN_REVIEW` (Revisión), `VERIFIED` (Verificado) y `DONE` (Completado).
   - Panel lateral con criterios de aceptación, historial de ejecuciones y revisiones de auditoría.
   - Frontera de seguridad: el diff completo de patch proposals está restringido a rol auditor y no es solicitado por la interfaz.

5. **Aislamiento y Modo Demostración:**
   - Modo `DEMO` segregado con fixtures sintéticas rotuladas y banner persistente.
   - Modo `LIVE` conectado directamente con la API FastAPI same-origin.
   - Limpieza inmediata de caché (`queryClient.clear()`) al alternar entre modos o al cerrar sesión.
   - Retención de credenciales (`X-Agent-Token` / `X-CEO-Token`) estrictamente en memoria volátil.

6. **Preservación de la Consola Heredada:**
   - La raíz `/` y los archivos `frontend/index.html`, `frontend/control-center.css`, `frontend/control-center.js` permanecen inalterados.
   - 100% de compatibilidad con `tests/test_control_center_ui.py`.

---

## Pila Tecnológica

- **Frontend:** React 19, TypeScript 5.7, Vite 6
- **Estado y Caché:** TanStack Query 5
- **Validación de Contratos:** Zod 4
- **Estilos:** Variables y tokens CSS nativos (sin dependencias pesadas de runtime)
- **Pruebas:** Vitest 5, Testing Library (50 tests unitarios y de contrato pasando)
- **Tamaño de Bundle:** ~126 KB gzip (muy por debajo del límite de 250 KB)

---

## Inicio Rápido

```bash
cd frontend/app
npm install
npm test
npm run build
npm run preview
```

Para más detalles, consulte la documentación en `docs/`:
- `docs/api-contract-inventory.md`: Inventario detallado de endpoints, cabeceras y códigos.
- `docs/architecture-decision-records.md`: ADR 001, ADR 002 y ADR 003.
- `docs/integration-and-operations.md`: Guía de despliegue, desarrollo y seguridad.
