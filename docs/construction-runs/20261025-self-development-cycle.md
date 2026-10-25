# Operación real del ciclo AAO Self Development (2026-10-25)

Instancia de **desarrollo**: PostgreSQL `compose.dev.yaml` (volumen persistente, migraciones 001–014) y API `aao.work_management_api` en `127.0.0.1:8001`. Proyecto del mandato `9d17d6c1-d644-424a-a425-fe7e084c3d91` («AAO — Self Development»). Todos los datos de abajo salen de `GET /v1/projects/{id}/board` y `GET /v1/projects/{id}/activity`; nada está simulado.

## Límites que conviene leer primero

- **Agente:** backend `fixture`. El proveedor `codex` sigue desactivado por defecto (ver `CODEX_PROVIDER_ACTIVATION_E2E.md`). El parche lo escribió Claude y el runner lo aplicó en el clon desechable. Clon, commit candidato, sandbox, propuesta, revisión, publicación y estado son los reales.
- **Auditor y publicador:** son principales separados en AAO (`aao-auditor-202610251032` de tipo AUDITOR, `aao-publisher-202610251032` de tipo AGENT con `code.publish`), pero los operó Claude. La revisión incluyó leer el diff y, desde el intento 3, ejecutar la suite completa sobre el candidato.
- **GitHub:** se usó el modo `--github gh` (régimen de construcción): la rama y la PR las crea la cuenta del operador, no las Apps de AAO. En modo `gh`, el publicador hace los dos pasos (push y open).

## Tarea 1: `ac0724c9-1835-44c6-abd9-39ac6a22a20c`, documentar las migraciones 013/014

El intento `040cdade` terminó en **FAILED**: «patch path is outside the allowed source and test roots». La política de propuestas solo admite `src/` y `tests/`, y la restricción se mantiene. La tarea queda en IN_PROGRESS como evidencia. El cambio de documentación entra a mano en la PR del equipo constructor que acompaña este registro.

## Tarea 2: `e111e402-e58c-4e5e-bab7-0fa0af0e7807`, añadir los tests del runner y del publicador a `core-unit`

| Intento | Ejecución | Base | Candidato | Resultado |
|---|---|---|---|---|
| 1 | `cf37a733` | `8b6f337` | `29a1591` | SUCCEEDED (`core-unit` con 12 tests). APPROVE → **PR #104**. **La CI falló**: los tests que construyen repos de ejemplo no incluían los ficheros añadidos. El check del sandbox no lo detectó porque usa la lista `core-unit` del worker. PR cerrada → `work.pr_closed` → la tarea vuelve a IN_PROGRESS. |
| 2 | `d4fbc4e4` | `de0cb2a` | `c1b4d6c` | FAILED: el sandbox ejecutó un test **modificado** que lanza su propio bwrap, y eso no se puede anidar. Corrección: el runner solo ejecuta los tests que el parche **añade**. |
| 3 | `893468bf` | `de0cb2a` | `4256ebc` | SUCCEEDED. Reutiliza la propuesta `76a0a0c8` del intento 2, porque el parche es idéntico. El auditor ejecutó la suite completa sobre el candidato (635 passed). APPROVE `a79856a0` → push → **PR #106**. |

Cronología de la tarea 2 en la actividad (UTC):
`work.created` 10:33:26 → `execution.claimed/completed` → `work.patch_proposed` → `work.reviewed` APPROVE 10:33:45 → `work.candidate_pushed` → `work.pr_opened` #104 10:34:00 → `work.pr_closed` 10:38:46 → (intentos 2 y 3) → `work.reviewed` APPROVE 16:22:30 → `work.candidate_pushed` → `work.pr_opened` #106 16:22:36.

**Pendiente para cerrar el ciclo:** que el CEO fusione #106 con la CI en verde, y después ejecutar `publish_candidate.py --step reconcile`, que dejará la tarea en DONE con `work.completed` y el `merge_commit_sha`.

## Defectos encontrados por la operación real y corregidos

1. La PR cerrada sin fusionar dejaba la tarea bloqueada. Ahora vuelve a IN_PROGRESS y la publicación es idempotente por candidato.
2. El runner ejecutaba en el sandbox los tests modificados, que pueden requerir el host. Ahora solo ejecuta los añadidos.
3. Había una carrera en el cliente de veto (`manifest_audit._report_veto_to_supervisor`): si el supervisor rechazaba y cerraba la conexión antes de leer, se perdía su respuesta («Broken pipe»). Hacía fallar `test_supervisor_intake_rejects_a_peer_that_is_not_the_auditor_uid` en la CI de #104.
4. Una carencia del proceso, no del código: el check del sandbox no sustituye a la suite completa. El auditor ejecuta la suite sobre el candidato antes de aprobar, y la CI de la PR sigue siendo la puerta.
