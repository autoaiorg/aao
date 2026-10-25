# Matriz viva de construcción y aceptación AAO

La matriz convierte los diez criterios de [CEO-DEC-AAO-CONSTRUCTION-2026-10-25](decisions/CEO-DEC-AAO-CONSTRUCTION-2026-10-25.md) en trabajo verificable. **No es certificación, no congela candidato y no habilita autonomía.** La auditoría independiente se hará una sola vez al final, por Antigravity u otro revisor que no haya construido el candidato. Actualizar evidencia y SHA al cerrar cada incremento.

Estado inicial de esta matriz: revisión base `95d8427cea3d5748ca7041ee054cfc99ab5a8b72`; rama de construcción `feat/agents-office-aa-integration`. Las etiquetas «pendiente» significan trabajo de construcción/evidencia aún no resuelto, no fallo certificado.

| # | Criterio | Estado de construcción | Evidencia conocida / SHA | Trabajo concreto siguiente |
|---:|---|---|---|---|
| 1 | Revisión candidata funcional con SHA exacto | Diferido al final; no congelar ahora | Construcción activa desde `95d8427`; no hay candidato declarado | Completar incrementos y preparar un único candidato al cierre |
| 2 | Raíz de confianza instalada y verificada sobre candidato | Base establecida; candidato pendiente | Instalación `0a55daf`, verifier PASS 38; intento `b392750` falló preflight de identidades y fue corregido después: `audit-runs/20261024-agy-r1-chain-b392750/README.md` | Repetir instalación/verificación una sola vez sobre el candidato final |
| 3 | Identidades separadas, privilegio mínimo y aislamiento probado | Parcial; falta ejercitar vía real | Cuentas Linux y GitHub Apps registradas en el handover; W2 escrito en `pr_publisher.py`, pero ciclos previos usaron `--github gh` | Runbook y ensayo W2 real: Apps `aao-impl-*` como cuentas de Apps al fork y `aao-pm` a PR; pasos sudo/cambio de cuenta reservados al CEO |
| 4 | Repositorio canónico protegido | Pendiente de comprobación live | Reglasets consultables en modo lectura; no se registra aquí resultado actual | Consultar `gh api repos/autoaiorg/aao/rulesets`, guardar salida saneada, SHA/fecha y contrastar reglas requeridas |
| 5 | Ensayos P2/P3 y negativos reproducibles | Pendiente | Procedimientos y evidencia de ensayos previos por revisar al cerrar candidato | Convertir cada requisito faltante en ejecución de ensayo con comandos, artefactos y SHA |
| 6 | Requisitos RA técnicamente satisfechos o excepción permitida | Pendiente | No se afirma PASS ni excepción en esta matriz | Mapear cada RA obligatorio a mecanismo y prueba reproducible; construir cobertura faltante |
| 7 | Auditoría independiente satisfactoria | Aplazada expresamente | GOV-REV-001: Codex construye y no audita independientemente su candidato | Solicitar revisión a Antigravity cuando esté disponible o a revisor no constructor; preservar independencia |
| 8 | Auditoría, supervisión, integración y recuperación operativas | Parcial; integrador permanece OFF | r1-chain identificó B-1 y B-2. En el código actual, B-1 tiene vía inbox firmada y despacho por auditor: `src/aao/integrator.py`, `src/aao/auditor_dispatch.py`, `tests/test_integrator_incident_dispatch.py`; no se concede escritura del ledger al integrador. B-2 (atribución provisional con ventana de 100 eventos) aún debe resolverse/verificarse | Construir solución a B-2 con atribución determinista; ensayar la cadena de incidente post-freeze y recuperación. No activar integrador en construcción |
| 9 | Ciclo R1 auténtico de tarea a integración registrada | No demostrado por W2; solo construcción de camino | Piloto Codex #114 no equivale a R1 por vía de Apps. `pr_publisher.py` contiene ruta W2; el integrador está OFF | Ejercitar W2 primero; después realizar ciclo R1 únicamente en ensayo de aceptación, no antes |
| 10 | Acta de aceptación CEO y alcance operativo | Diferido al cierre | Sin decisión de aceptación emitida | Presentar expediente final con capacidades que pasan a operación y las que siguen deshabilitadas; decisión reservada al CEO |

## Registro de incrementos

| Revisión / SHA | Incremento | Evidencia | Limitación |
|---|---|---|---|
| Rama `feat/agents-office-aa-integration`, cambios aún sin commit | Agents Office diferencial, inspiración registrada y F0 `/v1/organization` derivado de PostgreSQL | Prueba PostgreSQL focal `1 passed`; `649 passed` suite backend completa; `compileall`, Ruff, `pip check`, `git diff --check`; frontend TypeScript y 139 tests pasan | Sin CI remota ni merge observados; no independiente; F0 no crea perfiles de departamento ni heartbeat |
| `e807a5f8f9b3863609065ab9fb5a49ac6ff7a4dd` | PR #129 fusionada; F0 y documentación/matriz incorporados | CI de PR verde (backend + frontend) y CI de `main` verde en `e807a5f`; ver URL PR #129 | No independiente; F0 sigue siendo proyección de observaciones, no organigrama canónico |
| `feat/office-work-navigation`, trabajo local no commit | F1: navegar desde una asignación real al Kanban con su `projectId` | TypeScript y `frontend/app/src/test/office.test.tsx`: 18 passed | Falta suite completa, CI remota y merge |

## Reglas de mantenimiento

- Anotar SHA exacto y URL/artefacto de evidencia; actualizar solo criterios afectados por un cambio.
- En construcción, traducir brechas a tareas de implementación, como arriba; no ejecutar el paquete de certificación ni congelar un candidato.
- Un test local o CI verde acredita solo ese test/CI; nunca auditoría independiente ni aceptación del CEO.
- El integrador sigue OFF hasta el ensayo R1 reservado para aceptación. No ampliar escritura del ledger como remedio de B-1.
