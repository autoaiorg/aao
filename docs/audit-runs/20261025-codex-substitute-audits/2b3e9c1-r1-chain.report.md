Recusación declarada: Codex participó en el código auditado. Continúo bajo **CEO-DEC-AUDIT-CODEX-2026-10-24** como auditor sustituto, con independencia limitada. Los hallazgos sobre código de Codex llevan `self-authored`.

**Veredicto: REJECT**

Lo motivan exclusivamente los hallazgos A siguientes. Son conclusiones de análisis estático; no ejecuté reproducciones ni pruebas.

1. **A-01 — Una aprobación almacenada puede sobrevivir a un REJECT posterior. `self-authored`.**  
   El dispatch omite volver a evaluar el gate cuando ya existe un resultado para el mismo M ([auditor_dispatch.py:291](/tmp/tmp.fV8f6EnGPk/repo/src/aao/auditor_dispatch.py:291)). El bucle reutiliza ese resultado ([r1_pipeline.py:286](/tmp/tmp.fV8f6EnGPk/repo/src/aao/r1_pipeline.py:286)). Si posteriormente otra auditoría registra REJECT para el candidato, `promote()` verifica firmas, vetos e incidentes, pero no exige que `expediente_sha256` corresponda a la última decisión ([integrator.py:284](/tmp/tmp.fV8f6EnGPk/repo/src/aao/integrator.py:284)).

   Así, con autorización todavía vigente, latido actualizado y checks anteriores verdes, puede publicarse M pese al REJECT posterior. La comprobación que lo impediría existe en [manifest_audit.py:517](/tmp/tmp.fV8f6EnGPk/repo/src/aao/manifest_audit.py:517), pero queda fuera de esa promoción. Debe vincularse la publicación a la decisión actual del ledger e invalidarse el gate almacenado cuando cambie.

2. **A-02 — Un veto admitido después de la lectura inicial no impide la publicación en curso. `self-authored`.**  
   `promote()` lee el ledger, el latido y los marcadores antes de las operaciones remotas ([integrator.py:232](/tmp/tmp.fV8f6EnGPk/repo/src/aao/integrator.py:232), [integrator.py:255](/tmp/tmp.fV8f6EnGPk/repo/src/aao/integrator.py:255)). Antes del push solo vuelve a consultar la base; después publica sin releer esos controles ([integrator.py:376](/tmp/tmp.fV8f6EnGPk/repo/src/aao/integrator.py:376)).

   El intercalado permitido es: lectura sin veto → auditor registra veto y supervisor lo confirma → publicación de M. El CAS sobre `main` no detecta ese cambio. Hace falta coordinar la admisión del veto con la publicación mediante un mecanismo que impida usar una decisión invalidada durante ese intervalo.

Estos dos defectos afectan al flujo conservado en HEAD; no los presento como regresiones introducidas íntegramente por este diff.

3. **B-01 — La emisión de autorización puede quedar bloqueada permanentemente. `self-authored`.**  
   Tras registrar la auditoría, el dispatch intenta emitir inmediatamente la autorización ([auditor_dispatch.py:269](/tmp/tmp.fV8f6EnGPk/repo/src/aao/auditor_dispatch.py:269)). Si el supervisor aún no ha anclado esa nueva fila, la verificación rechaza por «ledger not yet anchored». En las siguientes ejecuciones, la existencia del informe hace que se omita la petición ([auditor_dispatch.py:247](/tmp/tmp.fV8f6EnGPk/repo/src/aao/auditor_dispatch.py:247)). Falta reintentar la emisión pendiente. La prueba E2E introduce expresamente el latido mediante un reemplazo del emisor ([test_r1_runtime_e2e.py:303](/tmp/tmp.fV8f6EnGPk/repo/tests/test_r1_runtime_e2e.py:303)), ocultando esa dependencia operativa.

4. **B-02 — La resolución normal no admite el incidente nuevo. `self-authored`.**  
   El dispatch guarda el identificador en `incident.id` ([auditor_dispatch.py:223](/tmp/tmp.fV8f6EnGPk/repo/src/aao/auditor_dispatch.py:223)). La resolución busca un `id` superior; además, `append()` sigue aceptando únicamente incidentes de tipo `incident` ([governance_ledger.py:68](/tmp/tmp.fV8f6EnGPk/repo/src/aao/governance_ledger.py:68)). Incluso habilitando una autoridad resolutora, la ruta normal no puede cerrar esos registros `integrator-incident`. Deben unificarse el formato y las comprobaciones de escritura y lectura.

5. **B-03 — El arnés genera identificadores que rechaza el control de equivalencia. `self-authored`.**  
   El arnés genera `AAO_TRIAL_RUN_ID` con un punto antes de los nanosegundos ([run_trial.sh:149](/tmp/tmp.fV8f6EnGPk/repo/scripts/trial/run_trial.sh:149)); el control solo admite letras, números y guiones ([github_trial.py:574](/tmp/tmp.fV8f6EnGPk/repo/src/aao/github_trial.py:574)). Cuando alcanza esa validación, el ensayo real falla antes del control positivo del fork. Debe probarse el formato que produce el propio arnés.

6. **C-01 — No puede afirmarse que toda prueba negativa detecte la retirada de su control. `self-authored`.**  
   Por ejemplo, `test_inline_write_permission_is_caught` comprueba una copia literal de la expresión regular, sin pasar el YAML adversario por el verificador principal ([test_workflow_invariants.py:35](/tmp/tmp.fV8f6EnGPk/repo/tests/test_workflow_invariants.py:35)). Retirar esa comprobación del verificador no haría fallar este caso. No ejecuté mutaciones.

**Respuestas al encargo**

| Pregunta | Resultado |
|---|---|
| 1. Controles para llegar a `main` | **La garantía conjunta falla por A-01 y A-02.** Identifiqué comprobaciones de firma, clase R1, checks sobre M, padres/árbol, CAS, identidad de App y PASS del host; su presencia no subsana esas elusiones. |
| 2. Escritura entre roles | No identifiqué una nueva escritura directa entre uids no autorizados en el diff. La custodia efectiva del host queda sin verificar. El contrato documenta que agentes interactivos comparten la cuenta del CEO con acceso a root mediante Docker ([contrato:168](/tmp/tmp.fV8f6EnGPk/repo/docs/AUDIT_MANIFEST_CONTRACT.md:168)). |
| 3. Fuga de tokens | No identifiqué una fuga concreta a argv, archivos o sandbox: las rutas examinadas pasan credenciales Git por entorno y limpian el entorno del candidato. No se verificó dinámicamente. |
| 4. Registro estático/root por PR | No observé datos por PR en el registro generado ni necesidad de root en el recorrido ordinario. La instalación y actualización de confianza siguen siendo operaciones privilegiadas. |
| 5. Sensibilidad de pruebas negativas | **No demostrada**, con el contraejemplo C-01 y la sustitución señalada en B-01. |

**Registro de ejecución y cierre**

- **Revisión:** HEAD confirmado en `2b3e9c16e520c21b2f9de15aeb9f442d7f36bc1c`.
- **Alcance:** los 33 archivos del diff solicitado desde `0a55daf5ee08c7f10c6c56224da145228c549011`, el contrato y las dependencias de confianza pertinentes.
- **Acciones:** lectura estática mediante los comandos Git permitidos. Sin modificaciones, commits, push ni merge.
- **Pruebas ejecutadas:** ninguna. No ejecuté pytest, CI, ensayos de GitHub ni verificaciones del host.
- **Limitaciones:** autoría compartida; sin validación del despliegue ni reproducción dinámica. Este informe no acredita auditoría plenamente independiente.
- **Autoridad:** encargo de solo lectura y excepción CEO indicada.
- **Bloqueadores y siguiente responsable:** PM y propietarios deben corregir A-01/A-02, aportar pruebas de ambas secuencias y someter el nuevo SHA a revisión. La auditoría retroactiva de Antigravity continúa pendiente.