# Auditoría independiente de Antigravity: cadena R1 y raíz de confianza en 592d807 (2026-10-24 12:46 UTC)

**Veredicto: APPROVE-TECHNICAL.** Hay 0 hallazgos A, 4 B y 2 C. Este dictamen habilita técnicamente `host_bootstrap.sh --trust-root-upgrade` sobre `592d807`. **El PM recomienda no ejecutar la actualización todavía.** Primero se corrige un lote: B-1, B-3 y el defecto PM-1, descrito abajo, que la auditoría no detectó. Después se hace una nueva auditoría y una sola actualización.

| Campo | Valor |
|---|---|
| Auditor | Antigravity CLI 1.4.4, uid `aao-auditor-alt` (1006), resolución delegada en #25 |
| Rango | `ef1913799fa5c04534f7f2204ff9d5f7de4eb1d4..592d80713b8ca9d7586037861d401adc7a67be58` (#59 a #80) |
| Prompt | `docs/audit-prompts/r1-chain.md`, sha256 de la plantilla `3ddba537…` |
| Informe | [`report.md`](report.md), sha256 `ec3c7d18d205227d118da28d126f1401afa7140122646513ecde48ab08853967` |
| Atestación | [`attestation.json`](attestation.json), sha256 `53c1a472df636f1b8d6e7e8d1d642c8e0449dbe55a72bcd52c36a695e6cf0749` |

**Procedencia.** El CEO ejecutó el auditor como `aao-auditor-alt`. El PM copió el informe y la atestación sin modificarlos. Los hashes coinciden con la salida del CEO.

## Triaje del PM

El triaje lo hizo Claude, que actúa como PM. No es una revisión independiente.

| Hallazgo | Verificación del PM | Acción |
|---|---|---|
| B-1: `issue_authorization` solo acepta `registry.json` propiedad de uid 0, pero en el host pertenece a `aao-trust` | Confirmado en `src/aao/authorization_issuer.py:93`. `anchor_owner_uids` vale `(0,)` por defecto. El test usa `os.getuid()` y por eso no lo detecta. | Corregir. Añadir un test con un propietario distinto de root y del uid del test. |
| B-2: P4 llama a `systemctl --user` en cuentas sin sesión | Confirmado: `aao-impl-{claude,codex,ag}` no tienen linger ni `/run/user/<uid>`. | Corregir en `run_trial.sh`. Ver B-01 de la auditoría del ensayo. |
| B-3: la atribución solo lee los eventos del repositorio canónico, no los de los forks | Confirmado. | Corregir junto con PM-1. |
| B-4: ante una divergencia tras el push, el integrador se congela pero no puede escribir el incidente en el ledger | Confirmado. Falla en cerrado. | **No** se dará al integrador acceso de escritura al ledger ni al anchor, porque rompería la custodia. Queda abierto y debe cerrarse antes de `--enable-integrator`. |
| C-1, C-2 | Observaciones. | Opcionales en el lote. |
| **PM-1 (nuevo, no detectado por la auditoría)**: la API de eventos de GitHub ya no incluye `payload.commits` en `PushEvent`. Las claves observadas son `before, head, push_id, ref, repository_id`. | Verificado el 2026-10-24 con `GET /repos/autoaiorg/aao/events` y `GET /repos/autoaiorg/aao-trial-codex/events`. `attribution()`, tanto en ef19137 como en 592d807, lanza `malformed GitHub push event` ante el primer `PushEvent`. Hoy registra `candidates: 0` solo porque el repositorio configurado todavía no tiene eventos de push. | Corregir: atribuir por `payload.head` y la cadena de `ref`. Añadir un test con la forma real del payload. |
