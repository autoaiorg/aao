# Auditorías sustitutas de Codex (excepción CEO-DEC-AUDIT-CODEX-2026-10-24)

**Auditor:** Codex 0.164.0, ejecutado como `aao-auditor-alt` mediante `scripts/audit/run_codex_audit.sh`. Usa una sesión propia, el binario fijado y modo de solo lectura.

**Independencia limitada.** Codex escribió parte del código auditado. En cada informe lo declara y marca esos hallazgos como `self-authored`.

**Procedencia:** el CEO lanzó las auditorías y el PM copió informes y atestaciones sin modificarlos.

| Revisión | Prompt | Veredicto | Informe (sha256) | Notas |
|---|---|---|---|---|
| `b8f23f9` | r1-chain | — | — | Antigravity: cuota agotada (`RESOURCE_EXHAUSTED`) antes de empezar, sin informe. Motivó la excepción. |
| `dab4df1` | r1-chain | — | — | El runner de Codex se negó a arrancar porque `~/.codex` era escribible por el grupo (login hecho con umask 002). Corregido en #92. |
| `bc742a2` | r1-chain | VETO por entorno, sin dictamen | `55b105ac…` | Codex no pudo ejecutar ningún comando: faltaba `codex-code-mode-host`. Además descargó plugins remotos. Corregido en #93. |
| `bc742a2` | p2p3-trial | — | — | El runner se negó por la caché de plugins descargada en la ejecución anterior. |
| `50033ae` | r1-chain | — | — | Primer intento: 401 con la sesión anterior, sin informe. El directorio se apartó como `-failed-`. |
| `50033ae` | r1-chain | **REJECT** | `040fdd3c…` | A-01 canal de incidentes, A-02 git como root sobre el árbol del auditor, A-03 rutas de seguridad en R1. Corregido en #94. |
| `50033ae` | p2p3-trial | **REJECT** | `df11a78d…` | A-01 a A-05. Corregido en #94. |
| `2b3e9c1` | r1-chain | **REJECT** | `7b7b1660…` | A-01 decisión vigente del ledger no vinculada, A-02 veto entre la lectura y el push. Defectos anteriores a este lote. Se corrigen en la PR siguiente. |
| `2b3e9c1` | p2p3-trial | **REJECT** | `403c14f0…` | A-01 el alcance de los tokens de App usaba un campo que la API no reconoce (`repository_names`, cuando la documentación oficial dice `repositories`). Afecta a producción. Además A-02 a A-04. Se corrige en la PR siguiente. |

Ninguna de estas auditorías ha autorizado nada: no hubo ningún APPROVE-TECHNICAL. La raíz de confianza sigue en `0a55daf` y el integrador apagado.

La auditoría retroactiva de Antigravity sigue siendo obligatoria cuando recupere la cuota.
