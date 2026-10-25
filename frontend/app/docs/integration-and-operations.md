# Guía de Operaciones e Integración — AAO Control Center

**Aplicación:** `frontend/app`  
**Tecnología:** React 19, TypeScript 5.7, Vite 6, TanStack Query 5, Zod 4, Vitest 5  
**Fases completadas:** F1 (Shell, navegación, adaptadores, tokens) + F2 (Dashboard CEO, Cartera, Detalle, Kanban 6 estados, Decisiones y Alertas de solo lectura)

---

## 1. Requisitos Previos

- Node.js >= 20 (Probado y verificado en Node.js v24.15.0 y npm 11.12.1).
- Python 3.12+ (para ejecutar la API FastAPI y los tests de regresión en `tests/test_control_center_ui.py`).

---

## 2. Comandos Operativos

Todos los comandos deben ejecutarse dentro del directorio `frontend/app`:

```bash
cd frontend/app

# Instalar dependencias limpias según lockfile
npm install

# Ejecutar suite de pruebas unitarias, de contrato y accesibilidad (Vitest)
npm test

# Ejecutar compilación de producción TypeScript + Vite
npm run build

# Previsualizar la compilación de producción en servidor local
npm run preview

# Iniciar servidor de desarrollo con Hot Module Replacement (HMR) y proxy a :8000
npm run dev
```

---

## 3. Integración con el Backend FastAPI

En modo desarrollo (`npm run dev`), Vite está configurado con un proxy inverso en `vite.config.ts`:
- `/v1/*` -> `http://127.0.0.1:8000/v1/*`
- `/health` -> `http://127.0.0.1:8000/health`
- `/ready` -> `http://127.0.0.1:8000/ready`

Esto permite consultar la API FastAPI en el mismo origen sin requerir cabeceras CORS en el servidor.

Para iniciar la API de backend en un entorno de desarrollo:
```bash
# Desde la raíz del repositorio o worktree
uvicorn aao.work_management_api:app --reload --port 8000
```

---

## 4. Modelo de Seguridad y Credenciales

1. **Memoria volátil estricta:**
   - Las credenciales (`X-Agent-Token` o `X-CEO-Token`) se almacenan únicamente en el estado volátil de React (`AuthContext`).
   - Está prohibido el uso de `localStorage`, `sessionStorage`, cookies o parámetros URL para persistir tokens.
   - Cerrar la pestaña o pulsar «Desconectar» purga inmediatamente la memoria y vacía toda la caché de consultas.
2. **Segregación Demo / Live:**
   - El modo Demo opera con fixtures estáticas aisladas.
   - Cambiar entre modos limpia la caché de datos de inmediato.
   - En modo Demo se muestra un banner naranja permanente indicando que los datos no proceden del núcleo de producción.
3. **Frontera de autorización:**
   - La interfaz observa el estado y no realiza mutaciones operativas.
   - No se incluye ningún botón para aprobar mandatos, fusionar PRs o activar niveles R2/R3.
   - El endpoint de diff de patch proposal (`/v1/work/{id}/patch-proposals/{id}`) no se solicita desde sesiones de lectura ordinarias.

---

## 5. Coexistencia con la Consola Clásica

- La consola histórica servida en `/` (`frontend/index.html`) permanece 100% inalterada.
- Los 23 tests de regresión en `tests/test_control_center_ui.py` continúan pasando sin fallos:
  ```bash
  pytest -q tests/test_control_center_ui.py
  # Resultado: 23 passed
  ```
- La barra lateral de la nueva interfaz incluye un enlace permanente `← Consola Clásica (/)` para retornar a la consola anterior en cualquier momento.
