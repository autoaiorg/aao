# CEO-DEC-AUDIT-CODEX-2026-10-24: Codex como auditor sustituto mientras Antigravity no tiene cuota

**Fecha:** 2026-10-24, unos minutos antes de medianoche CEST.

**Autoridad:** CEO, decisión R3 de excepción.

**Registra:** Claude (PM).

auditor_sustituto: codex

## Hechos

- El 2026-10-24, a las 21:44 UTC, `run_agy_audit.sh` falló con `RESOURCE_EXHAUSTED (429): Individual quota reached … Resets in 145h41m`, unos 6 días. No hubo dictamen. Registro: `~/.local/state/aao/sessions/2026/10/aao-session-20261024T214441Z/session.log` del CEO.
- El CEO no autoriza gasto ni esperar una semana.
- El PM comprobó que **no hay alternativa independiente sin coste en este host**:
  - Gemini CLI necesita Node 20 o superior;
  - el Node del sistema, propiedad de root, es la versión 18.19;
  - el Node 24 está en `~/.nvm`, escribible por los agentes, así que no sirve para un auditor.
- Codex 0.164.0 es un binario estático. El PM verificó que el binario local es idéntico al asset oficial `codex-x86_64-unknown-linux-musl` de la release `rust-v0.164.0` de `openai/codex`, con sha256 `b93f6811d3f653f0fb83be4050d857fb9abbb111dfa2ce160563327daff7f306`.

## Decisión

> «si es estrictamente necesario autorizo la exención para usar codex en lugar de antigravity, no podemos esperar 1 semana y no quiero invertir ahora ningun dinero» (CEO)

Codex sustituye a Antigravity como auditor, con estos límites.

## Límites y condiciones

1. **Identidad y custodia: las mismas que con Antigravity.**
   - Se ejecuta solo como `aao-auditor-alt`, mediante `scripts/audit/run_codex_audit.sh`.
   - Usa una copia root-owned de `/usr/local/bin/codex` con el hash fijado.
   - Usa una sesión de Codex propia de esa cuenta: el CEO hace `codex login --device-auth` como `aao-auditor-alt`. Ninguna credencial se copia de otra cuenta.
   - Trabaja en modo de solo lectura (`--sandbox read-only --ephemeral`), sobre un clon público en el SHA fijado y con el prompt revisado.
   - Produce el mismo informe y la misma atestación, con `"auditor":"codex"` y `"exception":"CEO-DEC-AUDIT-CODEX-2026-10-24"`.
2. **La independencia es limitada y se declara.** Codex escribió partes del código auditado: el canal de incidentes B-1, el supervisor watch y correcciones de `github_trial.py`. Además comparte proveedor y método de trabajo con el implementador. Por eso el prompt le exige declarar la recusación, auditar todo el alcance y marcar `self-authored` cada hallazgo sobre su propio código. **Un APPROVE de Codex sobre código propio no equivale a una auditoría independiente.**
3. **El bootstrap solo acepta la atestación de Codex con esta decisión.** El CEO debe pasar `--audit-exception CEO-DEC-AUDIT-CODEX-2026-10-24`. Ese identificador tiene que existir como archivo en la revisión fijada, y la atestación tiene que llevarlo. Sin él, el gate solo acepta `antigravity`.
4. **Alcance.** Cubre la auditoría r1-chain y p2p3-trial de la revisión que cierra el lote #90, es decir, la que la incluye y las correcciones de la preauditoría, y también el dictamen p2p3-dictamen sobre esa evidencia. No cubre ninguna otra revisión posterior sin una nueva decisión del CEO.
5. **Auditoría retroactiva obligatoria.** Cuando Antigravity recupere la cuota, alrededor del 2026-10-30, audita ese mismo rango con los mismos prompts. Si emite REJECT o encuentra un hallazgo A:
   - el integrador se congela, o no se activa si aún no lo estaba;
   - se aplican las correcciones;
   - los resultados que dependían de esa auditoría vuelven a quedar pendientes.
6. **Activación del integrador.** Esta excepción no autoriza por sí misma `--enable-integrator`. Esa decisión sigue reservada al CEO y se toma con las condiciones de CEO-DEC-P2P3-2026-10-24. El PM recomienda no activar el integrador hasta tener la auditoría retroactiva de Antigravity.
7. **Caducidad.** La excepción caduca cuando se completa la auditoría retroactiva, o el 2026-11-07, lo que ocurra antes.

## Riesgo residual que el CEO acepta

Mientras dure la excepción, la garantía de independencia de la auditoría queda reducida al control de segunda línea de un auditor que también es autor de parte del código, y la auditoría de Antigravity pasa a ser posterior. El riesgo lo acotan:
- la custodia separada, porque Codex corre como `aao-auditor-alt` y no como el implementador;
- el binario y el prompt fijados por hash;
- la condición de reversión del punto 5.
