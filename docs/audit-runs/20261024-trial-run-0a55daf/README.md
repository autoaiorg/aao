# Actualización de la raíz de confianza y primer ensayo P2/P3 en vivo (0a55daf, 2026-10-24)

**Ejecutó:** el CEO, con sudo, siguiendo [`CEO_RUNBOOK_TRUST_ROOT_UPGRADE.md`](../../procedures/CEO_RUNBOOK_TRUST_ROOT_UPGRADE.md).

**Revisión del arnés:** `0a55daf5ee08c7f10c6c56224da145228c549011`, con auditoría p2p3-trial APPROVE-TECHNICAL ([registro](../20261024-agy-p2p3-trial-0a55daf/README.md)).

**Análisis:** Claude (PM). No es una revisión independiente.

## Raíz de confianza: actualizada a 0a55daf

Registro: [`trust-root-upgrade.log`](trust-root-upgrade.log), sha256 `ff242427…`.

Resultado:
- verificación de Apps 9/9;
- auditoría aceptada (informe `6ff881a2…`);
- verificador del host `RESULT: PASS (38 checks)`;
- copia de la configuración anterior en `/var/backups/aao-trust-root/20261024T191258Z-ef19137…`;
- supervisor, reverificación y despacho del auditor activos;
- **el integrador sigue apagado**.

Antes hubo un intento fallido: la primera aplicación se detuvo en `realpath: /root/aao-keys` porque el procedimiento incluía `--keys-dir`. Falló antes de cualquier operación sobre la raíz de confianza.

## Ensayo P2/P3

Ejecución: `20261024T191333.488500113Z`, con `--only` sin A-02, P3-09, A-05 ni P3-06.

Archivos:
- evidencia: [`evidence-…tgz`](evidence-20261024T191333.488500113Z.tgz), sha256 `d42045f4…`; incluye `SHA256SUMS`;
- salida: [`run.log`](run.log), sha256 `39a97bb6…`;
- comprobación de secretos (PM): sin tokens ni claves.

Se excluyeron esas cuatro pruebas porque necesitan la PR de fixture, y el primer intento de ejecución falló al crearla (`gh: Invalid tree info (HTTP 422)`, defecto D6 abajo). Ese intento no dejó nada más que un blob suelto en el repo de ensayo.

| Prueba | Resultado | Diagnóstico del PM |
|---|---|---|
| A-01, P3-02 (×3 implementadores) | EQUIVALENCE-PENDING | Lo esperado. Pendiente de tu validación formal de la equivalencia (R3). |
| A-06, A-09, A-14 | **PASS** | |
| FORK-BRANCH | **PASS** | El implementador sube al fork un cambio de workflow con su App, y no tiene instalación en el repo de ensayo (404). |
| A-12 | NOT RUN | Lo esperado: la parte completa es manual. |
| A-03, A-04, P3-05 | FAIL | **D1, defecto del arnés:** la mutación `updateRefs` pedía el campo `refs`, que no existe (`undefinedField`). Falla antes de llegar a la protección. |
| P3-03 | FAIL | **D2, defecto del arnés:** GitHub rechazó correctamente con 422 *"2 of 2 required status checks are expected"* y `main` no cambió, pero el arnés solo aceptaba 403 y descartaba cualquier texto sobre checks. |
| P3-01 | INCONCLUSIVE | **D2:** GitHub rechazó con *"Cannot update this protected ref"*, y además la regla de PR y la de checks. El arnés buscaba el texto literal "restrict updates", que GitHub no imprime. |
| P3-07, P3-12 | INCONCLUSIVE | **D3, defecto del arnés:** el candidato salía de `main^`, que es anterior al workflow de CI (d1b55ef). El check `test` nunca aparece y se agotan los 300 s. |
| A-10 (×9) | FAIL | **D4, defecto del arnés:** `GET /installation` con un token de instalación devuelve 404 y los permisos quedan vacíos. Hay que leerlos con el JWT en `/repos/{o}/{r}/installation`. |
| A-11 | FAIL | **D5:** `head_repo` solo con el nombre da 422 (`head` inválido). Con `owner/name` da `fork_collab can't be granted…`: aao-pm no puede conceder ediciones del mantenedor sobre el fork. Se corrige con `maintainer_can_modify: false`. |
| P3-10 | NOT RUN | Depende de A-11. |

**Ninguna protección falló.** En todos los casos con FAIL o INCONCLUSIVE, GitHub denegó correctamente y `main` quedó intacto, o bien la prueba no llegó a ejecutarse. Ninguno de estos resultados cuenta como PASS. Se repetirán todos con el arnés corregido, D1 a D6, y una nueva auditoría p2p3-trial. D6 es la fixture del árbol: `gh -f 'tree[0][path]'` crea un objeto en lugar de un array, y se corrige enviándolo con `--input`.
