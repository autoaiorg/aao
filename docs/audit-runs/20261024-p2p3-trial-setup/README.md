# Preparación del ensayo P2/P3 en `autoaiorg/aao-governance-trial` (2026-10-24)

**Estado: preparado. El ensayo no se ha ejecutado.** RA-01, RA-02, RA-03, RA-07 y RA-09 siguen en PENDING, y el integrador está apagado.

## Hecho (por el CEO, con su cuenta de GitHub)

| Paso | Evidencia |
|---|---|
| Se crea el repo de ensayo, público | `autoaiorg/aao-governance-trial` (solo README) |
| Se instalan en él el integrador, ambos auditores, el supervisor, el notificador y el PM | Ver la autenticación de abajo; la atribución del supervisor pasa de HTTP 404 a `recorded` |
| Se crean los forks de ensayo de los implementadores | `autoaiorg/aao-trial-{claude,codex,agy}`, con padre `aao-governance-trial`; cada App de implementador está instalada solo en su fork |
| Se aplican los rulesets | 25776805 «A main: integrator only», 25776806 «B main+staging: integrity (no bypass)», 25776807 «C tags», todos activos; el token de workflow pasa a solo lectura |
| Autenticación 9/9 con el repo de ensayo | [`app-auth-trial-20261024T112513.jsonl`](app-auth-trial-20261024T112513.jsonl), sha256 `46661f72…`, sin secretos |

**Limitación de la autenticación 9/9.** La ejecutó `verify_app_auth.py` de `987f5cf` (#62). Ese código **aún no tiene auditoría independiente**: lo escribió Claude y el CEO lo fusionó sin revisión de otro autor. #60, #61, #62 y #64 entran juntos en la próxima auditoría de Antigravity. Hasta entonces, este 9/9 es operativo y no sirve como evidencia de RA.

## Qué falta para poner los RA en PASS

Los RA se cierran con las pruebas negativas del §16.1 al §16.5 de `AUTONOMOUS_GOVERNANCE_POLICY.md` (NT-01 a NT-09) y con el ensayo P2/P3 (A-01 a A-14, P3-01 a P3-12). La herramienta es `src/aao/github_trial.py`, que se ejecuta como el uid de cada rol. Para que sus resultados sirvan como evidencia de RA, tiene que ejecutarse desde un clon de root en un SHA auditado.

### Estado de cada prueba con la configuración actual

| Prueba | Rol | ¿Se puede ejecutar ya? | Motivo |
|---|---|---|---|
| A-10 | cada App | sí | Comprueba los permisos de la instalación; los implementadores, en su fork |
| A-06 | `aao-auditor`, y un implementador para el 403 | auditor: sí. Implementador: no en el repo de ensayo (no está instalado allí) | |
| A-09 | `aao-notifier` | sí | Crea una issue de prueba e intenta un push que debe rechazarse |
| A-03, P3-05 (RA-09) | `aao-integrator` | **no** | Primero hay que mover `main` a un candidato, y ese movimiento exige el check `test` (ruleset B) |
| A-04, P3-03, P3-07, P3-12 | `aao-integrator` | parcial | Necesitan un clon local con un commit candidato. Algunas mueven `main` y chocan con el mismo bloqueo |
| A-05, P3-06 (promoción) | `aao-integrator` | **no** | Sin un workflow que publique `test`, el ruleset B no deja integrar nada |
| A-01, A-02, P3-02 | implementador | **no** | La App no está instalada en el repo de ensayo, así que la herramienta no obtiene token y sale NOT RUN. **Hace falta decidir el criterio** (decisión 2) |
| P3-01, P3-09 | CEO | sí | Push y fusión con el token del CEO: deben rechazarse por el ruleset A |
| A-14 | `aao-probe-noworkflows` | **no** | Esa App no existe: no está en el registro y no tiene clave ni uid |
| A-07, A-08, A-11, A-13, P3-04, P3-08, P3-10, P3-11 | manual | manual | La herramienta las marca NOT RUN con los pasos manuales. A-12 es parcial |

### Decisiones del CEO

1. **Sembrar un workflow de CI en el repo de ensayo.** `main` está congelado en el README: los rulesets A y B están activos, B no admite excepciones y exige `test` y `aao-audit`, y el integrador no tiene el permiso `workflows`. Para que exista el check `test`, el CEO tiene que desactivar temporalmente A y B, subir un workflow mínimo y reactivarlos. Queda registrado como una acción del CEO sobre el repo desechable.
2. **Criterio de A-01, A-02 y P3-02.** El diseño de P2 instala las Apps de implementador solo en sus forks. Hay dos opciones: (a) contar como PASS que el implementador no pueda obtener token en el repo de ensayo, junto con A-10 en el fork; (b) instalar temporalmente la App en el repo de ensayo para demostrar el 403. AAO no redefine el criterio por su cuenta.
3. **A-14.** Crear la App `aao-probe-noworkflows` con su uid, o eximir la prueba de forma explícita.
4. **Paso pendiente de los rulesets.** En Settings > Actions del repo de ensayo, activar «Require approval for all outside collaborators». P3-10 depende de él.

## Decisiones del CEO (2026-10-24 11:32 CEST)

1. **Workflow de CI: autorizado.** Los rulesets A y B pueden desactivarse solo mientras se instala el workflow. Antes se guarda su configuración, después se restauran y se comprueba que los tres vuelven a estar activos. Si la protección no se restablece, se detienen las pruebas. Herramienta: `scripts/trial/seed_trial_ci.sh` (#66).
2. **A-01, A-02 y P3-02: opción (a), condicionada.** El 403 literal se sustituye por una demostración reproducible de que el implementador no tiene instalación ni permisos sobre el repo protegido. Se complementa con pruebas positivas en los forks y con una revisión adversarial. **No se declara PASS hasta que la equivalencia se valide formalmente.** La herramienta las marca `EQUIVALENCE-PENDING`, nunca PASS.
3. **A-14: no se exime.** Se crea la App temporal `aao-probe-noworkflows` con permisos mínimos y solo para el ensayo, se ejecutan las pruebas positiva y negativa, y al terminar se revoca la instalación. Herramienta: `scripts/trial/probe_app_setup.sh` (#66), con `--teardown` para la revocación.
4. **Actions: autorizado.** Se activa «Require approval for all outside collaborators», se guarda la evidencia y se ejecuta P3-10. Herramienta: `scripts/trial/actions_approval.sh` (#66).

**Auditoría obligatoria.** Un agente no recusado debe auditar #60, #61, #62 y #64, y la revisión definitiva de `github_trial.py` y del ejecutor del ensayo. Ningún resultado cuenta como evidencia de RA antes de esa auditoría. El integrador no se activa hasta que pasen NT-01 a NT-09, A-01 a A-14 y P3-01 a P3-12, y los RA correspondientes estén en PASS.
## Preparación ejecutada (2026-10-24, CEO)

- **Decisión 1, workflow de CI.** El workflow quedó en `main` del repo de ensayo con el commit `d1b55efca1453e51638d5302b5ba6095dee60dc5`. Los rulesets 25776805, 25776806 y 25776807 se restauraron **idénticos** a la configuración guardada; los hashes de antes y después coinciden. Evidencia en [`ci-seed/`](ci-seed/).
- **Decisión 4, Actions.** La aprobación pasó de `first_time_contributors` a `all_external_contributors`, y el token de workflow sigue en `read`. Evidencia en [`actions/`](actions/).
- **Decisión 3, sonda de A-14.**
  - App `aao-probe-noworkflows`: id 5453507, propietaria `autoaiorg`, permisos `contents: write` y `metadata: read`, sin `workflows`.
  - Instalación 174767813, solo en el fork `autoaiorg/aao-trial-probe` (padre: el repo de ensayo).
  - La clave está en el uid `aao-probe-noworkflows`, con modo 0600. La descarga se destruyó con `shred`.
  - **Incidencia:** el formulario del manifiesto devolvió «"url" wasn't supplied», así que el CEO creó la App a mano y generó la clave en GitHub. Los permisos coinciden con el manifiesto revisado.
  - Al terminar A-14 se ejecuta `probe_app_setup.sh --teardown`.
