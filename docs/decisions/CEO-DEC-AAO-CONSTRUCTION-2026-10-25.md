# CEO-DEC-AAO-CONSTRUCTION-2026-10-25
## Régimen de construcción y transición a operación autónoma

**Estado:** RATIFICADA por el CEO el 2026-10-25, con las precisiones del §8, y **en vigor desde esa fecha**  
**Autoridad:** CEO — decisión R3  
**Ámbito:** Proyecto AAO — Self Development

### 1. Objeto

Se establece una separación formal entre la fase de construcción de AAO y su posterior funcionamiento como organización digital autónoma.

La finalidad de esta decisión es permitir que AAO sea desarrollada eficientemente sin exigir que los mecanismos de gobierno autónomo todavía en construcción rijan las actuaciones del equipo que los está implementando.

### 2. Régimen de construcción

Hasta la activación formal de AAO:

- Claude, Codex y Antigravity actuarán como agentes externos de desarrollo bajo la dirección del CEO.
- Las operaciones de construcción no estarán sujetas a los gates de integración, clases R0–R3 ni auditorías formales obligatorias previstos para AAO en funcionamiento.
- El equipo podrá desarrollar, corregir, revisar y preparar integraciones utilizando un proceso ordinario de ingeniería de software.
- El CEO conservará la autoridad de integración y despliegue durante esta fase, pudiendo delegar operaciones técnicas expresamente cuando sea seguro hacerlo.
- Se mantendrán pruebas automatizadas, CI, revisiones técnicas proporcionales, control de versiones y trazabilidad de cambios relevantes.
- No se utilizarán las identidades autónomas de producción para eludir permisos o controles de seguridad durante la construcción.

Esta suspensión de exigencias procedimentales afecta exclusivamente a la construcción externa de AAO. No modifica los requisitos de seguridad que AAO deberá satisfacer para operar autónomamente.

### 3. Vigencia de las decisiones arquitectónicas

Se conservan como requisitos de la futura organización:

- La independencia funcional de auditoría.
- La separación de identidades y credenciales.
- El control de integraciones y el sistema de vetos.
- La clasificación de riesgos R0–R3.
- Las facultades constitucionalmente reservadas al CEO.
- La prohibición de acceso general de los agentes al Docker privilegiado del host.
- La protección de los repositorios y de la raíz de confianza.
- La trazabilidad y verificación de decisiones, pruebas y resultados.

Las decisiones anteriores continúan orientando el diseño, pero sus procedimientos operativos no se exigirán al equipo externo durante la construcción.

### 4. Criterios para el traspaso

Antes de transferir operaciones a AAO deberán cumplirse todos los criterios siguientes:

1. Una revisión candidata funcional, identificada por SHA exacto y congelada para aceptación.
2. Una raíz de confianza instalada y verificada sobre esa revisión.
3. Identidades de agentes y auditores separadas, con permisos mínimos y aislamiento probado.
4. Repositorio canónico protegido mediante reglas verificadas y sin excepciones no autorizadas.
5. Ensayos P2/P3 y pruebas negativas completados con evidencia reproducible.
6. Requisitos RA obligatorios técnicamente satisfechos, o excepciones residuales específicamente documentadas y autorizadas cuando la política las permita.
7. Auditoría independiente satisfactoria de la revisión candidata y de los mecanismos críticos.
8. Servicios operativos de auditoría, supervisión, integración y recuperación comprobados.
9. Demostración de un ciclo R1 auténtico, desde la tarea hasta la integración y su registro.
10. Acta de aceptación del CEO, indicando qué capacidades pasan a operación autónoma y cuáles permanecen deshabilitadas.

La activación inicial podrá limitarse a R1. No se entenderá incluida la autorización R2 ni ninguna competencia R3.

### 5. Procedimiento de transición

El PM del equipo externo preparará un expediente único de aceptación con el inventario de componentes, pruebas, auditorías, limitaciones y riesgos residuales.

El CEO decidirá sobre la activación basándose en dicho expediente.

Una vez activada AAO, las operaciones transferidas quedarán sometidas a sus políticas de gobierno, permisos, auditorías y mecanismos de control.

La construcción externa podrá continuar desarrollando capacidades no activadas, manteniendo separados los entornos y las autoridades.

### 6. Restricciones permanentes

Esta decisión no autoriza:

- La atribución de poderes constitucionales a agentes.
- La utilización insegura de credenciales privilegiadas.
- La exposición de secretos.
- La desactivación indiscriminada de controles técnicos de seguridad.
- La declaración ficticia de auditorías o pruebas satisfactorias.
- El uso de capacidades autónomas antes de su aceptación formal.

### 7. Instrucción de ejecución

El equipo externo debe priorizar la finalización de AAO Self Development y su Control Center, evitando reconstruir continuamente la raíz de confianza o repetir los ensayos integrales en cada cambio ordinario.

Los ensayos completos y la auditoría formal de aceptación se realizarán sobre candidatos de traspaso claramente identificados.

El objetivo es disponer de una organización funcional y transferirle gradualmente su operación, no convertir la fase de construcción en un ejercicio permanente de certificación.

### 8. Ratificación y precisiones del CEO (2026-10-25, texto literal)

> Ratifico **CEO-DEC-AAO-CONSTRUCTION-2026-10-25**, con las precisiones 1 y 2 propuestas y la siguiente modificación de la precisión 3:
>
> Durante la construcción acepto de forma transitoria el riesgo residual derivado del uso de las herramientas y credenciales actuales, exclusivamente en el entorno de desarrollo y dentro de los permisos ya autorizados.
>
> Esta aceptación no concede acceso general a secretos, privilegios de root ni capacidad de ejecutar operaciones irreversibles o sensibles sin autorización. El uso de Docker y GitHub deberá limitarse a las necesidades de construcción y mantener medidas razonables de protección.
>
> La separación definitiva de identidades, credenciales y privilegios será un criterio obligatorio del traspaso.
>
> La excepción de Codex como auditor y la auditoría retroactiva dejan de ser requisitos de integración durante la construcción. La auditoría independiente se realizará sobre el candidato de aceptación.
>
> Las decisiones anteriores sobre P2/P3, equivalencias, P3-10, rutas protegidas, Docker y bloqueo de activación se conservan como requisitos y restricciones para la operación autónoma futura, sin imponer sus gates a las PR del equipo constructor.
>
> **Ordeno aplicar desde ahora el régimen de construcción externa.**
>
> Actualiza la decisión formal y la PR #97, y reorganiza el proyecto para priorizar la terminación funcional de AAO Self Development y Control Center.
>
> Claude, Codex y Antigravity trabajarán como equipo constructor externo, con integración ordinaria y controles de calidad proporcionados.
>
> No solicites nuevas decisiones sobre los mecanismos de gobierno autónomo salvo que afecten a una materia estratégica o a un riesgo real que exija mi intervención.
>
> El objetivo inmediato es construir AAO. La certificación y transferencia de poderes vendrán después.

**Efectos sobre decisiones anteriores** (los registra el PM; no añaden nada a lo ratificado):
- **CEO-DEC-AUDIT-CODEX-2026-10-24:** deja de ser requisito de integración. La auditoría independiente se hará sobre el candidato de aceptación (criterio 7).
- **CEO-DEC-P2P3-2026-10-24 y CEO-DEC-2026-10-25:** siguen vigentes como requisitos y restricciones del traspaso y de la operación autónoma. Sus gates no se aplican a las PR del equipo constructor.
- **El riesgo de las credenciales del CEO** al alcance de los constructores es un riesgo transitorio aceptado. Su resolución es el criterio 3 del traspaso.
