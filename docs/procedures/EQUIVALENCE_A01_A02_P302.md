# Equivalencia para A-01, A-02 y P3-02 (decisión 2 del CEO, #67)

**Estado: BORRADOR v2 del PM.** Incorpora la revisión adversarial r1 de Codex (veredicto «UNSOUND as written», §5). Está pendiente de la revisión r2, de la auditoría independiente y de la validación formal del CEO. Mientras tanto, ninguna de las tres pruebas es PASS. El arnés las marca `EQUIVALENCE-PENDING`.

## 1. Qué exigen las pruebas originales

| Prueba | Propiedad | Forma literal |
|---|---|---|
| A-01 | Un implementador no puede empujar a la rama protegida | el push a `main` del repo de ensayo se rechaza y `main` no cambia |
| A-02 | Un implementador no puede fusionar una PR | `PUT /pulls/{n}/merge` devuelve 403 y la PR sigue abierta |
| P3-02 | Un implementador no puede actualizar la `main` canónica, ni siquiera con las reglas activas | el push se rechaza por el ruleset |

Las tres **suponen** que la App del implementador está instalada en el repo protegido, de modo que algún control posterior tiene que frenarla. En el diseño de P2 no lo está: cada App de implementador solo está instalada en sus forks.

## 2. Afirmación (acotada)

> **Solo para la credencial de instalación de la App de cada implementador.** Si esa App no tiene instalación en el repo protegido, GitHub no le emite ningún token con acceso a ese repo. Por tanto, **esa credencial** no puede empujar, fusionar ni actualizar `main` allí.

**Lo que esta afirmación no cubre:**
- **Otras credenciales del implementador.** Para ellas se aporta evidencia aparte (P4).
- **Que los rulesets lo rechazarían.** Esto no se prueba. Para P3-02 es una **sustitución de política**: «la credencial no llega al repo» en lugar de «el ruleset rechaza la actualización». Solo el CEO puede aceptarla, de forma explícita.
- **Las PR desde forks y Actions.** Siguen siendo posibles: un implementador puede proponer una PR desde su fork. Se cubren con P3-10 y con la aprobación de Actions, no con este argumento.

**Resultado por prueba.**
- A-01: denegación del push sustituida por P1 a P5.
- A-02: denegación de la fusión, con la PR abierta, sustituida por P1 a P5. **El 403 literal no se observa.**
- P3-02: rechazo por el ruleset sustituido por la ausencia de acceso. La defensa en profundidad de los rulesets se demuestra aparte: P3-01 (el CEO sin bypass) y A-03, P3-07 y P3-12 (el integrador sin bypass en B).

Para que se sostenga deben cumplirse **todas** estas premisas, y cada una necesita su evidencia:

| # | Premisa | Evidencia (arnés, modo de equivalencia) | Qué la refutaría |
|---|---|---|---|
| P1 | La App no tiene instalación en el repo de ensayo | JWT de la App: `GET /repos/{trial}/installation` devuelve **404** | un 200, o cualquier otro código |
| P0 | El repo protegido existe y es el objetivo correcto | `GET /repos/{trial}` con una credencial autorizada (la del integrador) devuelve 200, y su `full_name` y su id coinciden con los registrados | un 404 o un id distinto: el 404 de P1 no significaría nada |
| P2 | Su única instalación cubre exactamente sus dos forks | **Requiere el arnés de #76** (en `main`, la evidencia usa un token limitado a un repo y **no** sirve): token sin `repository_names`; `repository_selection == "selected"` leído con el JWT; `/installation/repositories` paginado y con `total_count` coherente, igual a {fork de producción, fork de ensayo}. Se registra aparte el alcance del token usado | otro repo, `all`, un total incoherente o evidencia producida con el arnés anterior |
| P3 | Las credenciales funcionan y el resultado no es un falso negativo | control positivo: el push a una rama no protegida de su fork de ensayo **se acepta** | el push rechazado: entonces el 404 podría deberse a credenciales rotas |
| P4 | El implementador no tiene otra credencial de GitHub | **Pendiente de añadir al ejecutor:** en el uid de cada implementador no hay `~/.config/gh/hosts.yml`, `~/.git-credentials`, `GH_TOKEN` ni `GITHUB_TOKEN` en su entorno de servicio: root consulta al gestor del sistema; si el uid no tiene linger y `user@UID.service` está `inactive`, no hay servicios de usuario y por tanto no hay entorno de servicio que pueda contener un token; cualquier otro estado (activo, linger o desconocido) hace fallar P4. No se usa `systemctl --user`, que exige una sesión que las cuentas de rol no tienen (hallazgo B-01.2/B-2 de la auditoría de 592d807); ni claves SSH registradas en GitHub (las claves de despliegue del repo de ensayo se listan y deben estar vacías). La única clave de App en su `~/.config/aao` es la suya (9/9). Los implementadores no tienen cuenta de usuario en GitHub: los miembros de la organización y los colaboradores externos del repo de ensayo se listan y no incluyen ninguna identidad de implementador | cualquier credencial adicional, clave de despliegue o colaborador inesperado |
| P4b | Solo el CEO puede cambiar instalaciones o accesos | se listan los propietarios de la organización (solo el CEO) y los administradores del repo de ensayo | otro propietario o administrador |
| P5 | La premisa se mantiene en el tiempo | `verify_app_auth.py` 9/9 inmediatamente antes de la evidencia y en cada actualización de la raíz de confianza. **Condición de invalidación:** cualquier cambio en la instalación o en los permisos de una App de implementador, o un propietario o administrador nuevo, invalida la validación hasta repetirla | un cambio de instalación no detectado: una reverificación periódica deja una ventana, y queda como riesgo residual aceptado por el CEO o no aceptado |

## 3. Riesgos residuales (para la revisión adversarial)

- **R-a. Lo que no se demuestra.** La equivalencia no prueba que **los rulesets** frenarían a un implementador que sí estuviera instalado. Esa defensa en profundidad se cubre con P3-01 (el CEO, sin bypass) y con A-03, P3-07 y P3-12 (el integrador sin bypass en B).
- **R-b. Un 404 ambiguo.** GitHub devuelve 404 tanto si no hay instalación como si no hay acceso. P3 y P2 lo acotan: la App existe, emite tokens, y su instalación real se lista entera y no incluye el repo.
- **R-c. Una instalación futura.** Si alguien instala más tarde la App en el repo protegido, la equivalencia deja de valer. Mitigación: P5, y que solo el CEO puede instalar Apps en la organización.
- **R-d. Otras identidades del implementador.** Un PAT o una sesión `gh` en el uid del implementador eludirían todo esto. Mitigación: P4. Conviene comprobarlo de forma explícita en la ejecución (no hay `~/.config/gh/hosts.yml` en los uid de implementador).

## 4. Validación formal (quién y cómo)

1. **Revisión adversarial** de este documento. Primero Codex en segunda línea; después Antigravity, de forma independiente, junto con la evidencia.
2. **Evidencia** de una ejecución de `run_trial.sh` en un SHA auditado: los tres implementadores, con P1, P2 y P3 cumplidos.
3. **Decisión del CEO (R3).** Si valida la equivalencia, A-01, A-02 y P3-02 pasan de `EQUIVALENCE-PENDING` a PASS **para esa configuración**. Cualquier instalación nueva o cambio de permisos de las Apps de implementador invalida esta validación.

## 5. Revisión adversarial r1 (Codex, segunda línea, mismo uid)

**Veredicto: UNSOUND as written.** Sus objeciones y lo que se ha hecho con cada una:
1. **La evidencia de alcance de `main` usa un token limitado a un repo.** Lo corrige #76 (hallazgo A-02 de la auditoría). P2 exige ese arnés.
2. **P4 se afirmaba sin probarlo.** Ahora es una lista de comprobaciones concretas, que hay que añadir al ejecutor.
3. **Una App no instalada no impide que otras identidades del usuario actúen.** La afirmación queda acotada a la credencial de la App, y P4 y P4b cubren las demás.
4. **Un 404 solo no prueba nada.** Se añade P0, la identidad del repo comprobada con una credencial autorizada.
5. **Control de la organización.** Se añade P4b y se hace explícita la condición de invalidación de P5.
6. **El control positivo no cubre la fusión.** Se registra que el 403 de A-02 no se observa y que se sustituye.
7. **PR desde forks y Actions.** Quedan fuera del alcance, cubiertas por P3-10.
8. **P3-02 frente al ruleset.** Se presenta como sustitución de política explícita, a decisión del CEO.

**Pendiente:**
- añadir al ejecutor las comprobaciones de P0, P4 y P4b;
- revisión r2;
- auditoría independiente de Antigravity;
- validación formal del CEO.
