# AAO: arquitectura Zero Trust y despliegue sin coste adicional

**Fecha:** 2026-10-27. **Estado:** arquitectura de destino conforme a las instrucciones
del CEO; propuesta de transporte y despliegue pendiente de aprobación. No acredita
instalación, exposición de servicios, cierre de B-2 ni aceptación del integrador.

**Presupuesto adicional máximo: 0 €.** Ninguna contratación, dominio comprado,
API de pago adicional, prueba con conversión a pago o ampliación automática.
Una cuota agotada produce indisponibilidad explícita, nunca facturación autorizada.

## 1. Decisión y límites de confianza

Tres planos con identidades, secretos y permisos separados:

```text
Dispositivo CEO + identidad con MFA
  └─ acceso PRIVADO aprobado ─► frontend / API administrativa
                                  │ autorización AAO por petición
                                  ▼
                         PostgreSQL privado (estado canónico)
                                  ▲
              PM / workers ── API operativa privada
                   │              │
                   └─ modelos y GitHub: conexiones salientes acotadas

GitHub ── HTTPS público ─► receptor aislado + buzón durable de transporte
                                    ▲
                  supervisor ── pull HTTPS saliente + confirmación
                       │ valida, corrobora y firma localmente
                       ▼
               recibos protegidos / atribución existente
```

El receptor externo no es el supervisor, no es una puerta de acceso al host y no
contiene estado de proyectos, tareas, autorizaciones ni ejecución. PostgreSQL
sigue siendo la única fuente de verdad del negocio. Los recibos protegidos
existentes conservan su función de evidencia; el buzón solo transporta entregas.

| Plano | Acceso permitido | Acceso prohibido |
|---|---|---|
| Administrativo | CEO autenticado, dispositivo autorizado; API comprueba sesión y autoridad AAO | Internet público; token CEO en agentes, receptor o relay |
| Operativo | PM y agentes con credenciales distintas y grants existentes, API privada | Convertir rol organizativo, recomendación o evento en permiso; suplantar CEO |
| Datos | API/worker autorizado según función; rol runtime mínimo | Puerto PostgreSQL público, receptor conectado a PostgreSQL, rol runtime superusuario |
| Recepción | POST de eventos acotados; pull/ack de transporte autenticado | Shell, herramientas, modelos, tokens de agentes, claves GitHub Apps, clave firmante supervisor, ledger o API administrativa |

No habilitar integrador autónomo. No cambiar raíz de confianza, custodia del ledger,
auditoría, reglas finales A/B o grants por una incidencia del transporte.

## 2. Acceso CEO: privado antes que remoto

**Despliegue de construcción actual:** loopback/local. No necesita contratar ni
activar una VPN para continuar el PM o el piloto. No hacer bind a `0.0.0.0`, abrir
puertos de router, añadir túneles públicos ni habilitar Tailscale Funnel.

**Tailscale evaluado, no activado:** identidad del CEO mediante IdP con MFA,
aprobación del dispositivo y política explícita mínima CEO → interfaz administrativa.
Sin regla global allow-all, subnet router, exit node ni acceso CEO directo al puerto
de PostgreSQL. Mantener autenticación AAO: pertenecer a la tailnet no concede
autoridad de negocio. MFA depende del IdP; no equivale a solicitar MFA en cada
petición HTTP. [MFA](https://tailscale.com/docs/multifactor-auth),
[políticas](https://tailscale.com/docs/features/access-control).

El plan Personal gratuito no está destinado a uso comercial. Existe una modalidad
Community para proyectos OSI elegibles, pero no se presume que AAO o la cuenta
actual estén admitidos. **No seleccionar Tailscale de pago ni basar el despliegue
en un trial.** Hasta verificar elegibilidad gratuita y aprobación de la política,
mantener acceso local. No inventar una identidad IdP, hostname o tailnet.
[Planes](https://tailscale.com/pricing),
[Community](https://tailscale.com/docs/reference/free-plans-discounts).

## 3. B-2: resultado de evaluar consultas salientes

**Pull puro no demuestra cobertura histórica íntegra.**

- Events API sirve para reconciliar, pero tiene ventana limitada y latencia; no
  prueba que un intervalo sin eventos sea un intervalo sin pushes. Paginar corrige
  el límite de una página, no crea historia que GitHub ya no conserva.
  [Límites oficiales](https://docs.github.com/en/rest/activity/events).
- La API de entregas recupera entregas de un webhook configurado; no sustituye al
  webhook ni reconstruye pushes anteriores a su configuración. La recuperación
  documentada abarca tres días y no hay reintento automático de GitHub.
  [Recuperación](https://docs.github.com/en/webhooks/using-webhooks/handling-failed-webhook-deliveries),
  [retención](https://docs.github.com/en/webhooks/testing-and-troubleshooting-webhooks/redelivering-webhooks).
- El JSON obtenido por API no garantiza bytes idénticos al POST original: no
  serializarlo de nuevo y afirmar que se verificó el HMAC de la entrega original.
- Autor/committer de un commit, firma de commit y quien hizo push son conceptos
  distintos. Una rama actual tampoco demuestra todos sus actores históricos.

Por tanto, conservar polling saliente para corroboración y recuperación, pero no
declararlo sustituto completo de un journal de entregas. Las lagunas quedan
provisionales/fail-closed. No configurar una URL ficticia para provocar fallos.

## 4. Transporte seleccionado y exposición justificada

**Diseño preferido:** receptor gestionado mínimo **Cloudflare Worker Free + D1
Free**, hostname incluido del proveedor, supervisor que extrae por HTTPS. No
requiere publicar el portátil, comprar dominio, abrir puertos ni alojar la API AAO
fuera del host. La cuenta, su elegibilidad y su plan real siguen sin comprobarse;
no hay autorización de despliegue por este documento.

Alternativa túnel HTTPS con nombre: reutiliza el receptor local, pero publica una
ruta del host y depende de que esté encendido; añade dominio/operación y no mejora
la recepción durante apagados. No seleccionada con los datos actuales. Quick
Tunnel temporal no es un endpoint operativo estable.

| Superficie externa | Justificación | Restricción |
|---|---|---|
| POST HTTPS `/github/push` en relay gestionado | GitHub necesita alcanzar un receptor; conservar durante caída del host | Solo push/ping esperado, cuerpo acotado, HMAC, allowlist de repositorios, sin ejecución |
| HTTPS pull/ack en el mismo relay | Supervisor inicia extracción y confirma persistencia | Credencial de transporte independiente, sin autorización AAO; límites de lotes y sin redirects |
| Salida supervisor → GitHub API | Corroboración independiente y recuperación | Identidad GitHub de supervisor, permisos mínimos; nunca credencial CEO o de un agente |
| Salida workers → proveedor autorizado/GitHub | Ejecución y W2 ya previstos | Cuenta existente y ámbito aprobado; no ampliar proveedor ni pago |

No se justifica ninguna otra entrada pública: ni frontend, API, PostgreSQL,
coordinador, SSH del host, métricas ni servicio de firma.

Free tiene cuotas finitas. Verificar plan y rechazo al agotarse antes de crear el
receptor; no incorporar tarjeta, upgrade, add-on ni recursos de pago. Configurar
límites de tamaño, backlog y consultas, sin prometer recepción ilimitada por 0 €.
Al alcanzar límites: error de recepción, conservar lo ya guardado, alerta local y
reconciliación; ninguna atribución automática de una cadena incompleta.
[Workers](https://developers.cloudflare.com/workers/platform/limits/),
[D1](https://developers.cloudflare.com/d1/reference/faq/).

## 5. Contrato de recepción, persistencia e identidad

1. Validar evento, repositorio permitido, UUID, tamaño y HMAC-SHA256 sobre bytes
   originales antes de aceptar. Comparación resistente a diferencias temporales.
   Un `ping` no crea recibo de push ni se interpreta como trabajo.
2. Guardar cuerpo original, cabeceras necesarias, digest y fecha en almacenamiento
   durable antes de responder 2xx. UUID repetido con mismo contenido es idempotente;
   contenido distinto con mismo UUID es conflicto, nunca sobrescritura.
3. Supervisor extrae lotes limitados, repite validaciones y conserva procedencia.
   Valida esquema estrictamente; datos externos nunca se interpolan en comandos.
4. **HMAC prueba posesión de un secreto compartido, no identidad del actor.**
   Corroborar con GitHub por canal independiente del relay: GUID/hook/repositorio,
   evento, sender con ID inmutable y transición before/ref/after. Resolver las Apps
   contra el registro verificado de identidades y relacionar con candidato,
   ejecución, revisión y PR persistidos en AAO. No confiar solo en `sender.login`,
   nombre parecido, autor del commit o ID de instalación recibido.
5. Si la fuente independiente no permite corroborar o la cadena no llega al origen
   exigido, mantener atribución provisional. Un payload firmado no puede promoverse
   por sí mismo a aprobación, grant, integración o resultado revisado.
6. Firmar localmente con la clave exclusiva del supervisor y persistir de forma
   durable. Solo después confirmar UUID en el relay. Conservar recibos aceptados
   y evidencia necesaria para reinicio; un ack no borra evidencia local.

La corroboración adicional de identidad y procedencia es trabajo de construcción
pendiente: el receptor existente valida HMAC y firma `sender.login`, pero eso no
demuestra por sí solo todos los requisitos anteriores. No declarar B-2 cerrado
por las pruebas unitarias del transporte. Cubrir canonical **y forks W2**.

## 6. Amenazas, recuperación y revocación

| Fallo/amenaza | Respuesta exigida |
|---|---|
| Host apagado | Relay conserva sin depender del host; pull tras reinicio. Si cuotas/retención agotadas, identificar laguna y no aceptar integración |
| Caída tras guardado local antes de ack | Repetir pull; UUID/digest idempotente, revalidar persistencia y repetir ack |
| Entrega perdida/rechazada | Consultar entregas GitHub y reintentar dentro de tres días; fuera de cobertura, provisional explícito, no inventar histórico |
| Duplicados/desorden | Clave única persistente, conflicto rechazado, reconstrucción por before→after y no por orden de llegada |
| DDoS/cuota agotada | Límites por petición/lote/backlog, consultas indexadas, fallo cerrado, nunca upgrade de pago |
| Secreto webhook filtrado | Suspender aceptación del intervalo afectado, rotar en GitHub y supervisor/relay; ventana de rotación corta y explícita, no fallback sin firma |
| Credencial pull filtrada | Revocar y rotar credencial de transporte; no da acceso a AAO/PG/firmante. Reconciliar posibles ack fraudulentos con journal local y GitHub |
| Relay comprometido | Tratar cuerpo y metadatos como no confiables aunque haya HMAC válido: el relay puede poseer ese secreto. Corroborar por GitHub independiente, cuarentena del intervalo y reprovisionar relay; si no se puede corroborar, no aceptar |
| Robo del dispositivo CEO | Revocar dispositivo/sesión e identidad según alcance; VPN no sustituye revocación AAO |

Nunca descartar automáticamente pendientes no confirmados para liberar espacio.
No existe garantía de disponibilidad ilimitada con cuotas gratuitas; la garantía
de seguridad es no convertir una pérdida de cobertura en evidencia afirmativa.

## 7. Despliegue, permisos, reversión y pruebas

**Orden:** PM funcional local y piloto → transporte externo aprobado → prueba B-2
→ aceptación final independiente en su momento. B-2 no bloquea asignación y
ejecución local del ensayo; sí bloquea cualquier afirmación de atribución completa
o aceptación del integrador que dependa de ella.

Antes de pedir intervención al CEO, entregar un único paquete con revisión exacta,
inventario read-only, comandos completos y valores verificados. Debe separar:

- instalación de runtime PM/worker bajo cuentas existentes (sudo solo humano);
- emisión/revocación de credenciales y grants por CEO, sin usar su token de dotenv;
- corrección del rol runtime PostgreSQL y permisos explícitos 033/035, sin
  eliminar permisos usados ni ejecutar agentes como propietario/superusuario;
- cuenta gratuita y hostname real del relay, permisos de despliegue limitados,
  secretos generados sin mostrarlos, configuración de hooks de canonical/forks;
- verificación de plan 0 €, pruebas, supervisión y reversión.

No entregar placeholders como valores comprobados. No pedir crear credenciales de
proveedor ni repetir la autorización OpenAI ya concedida.

**Reversión:** detener pull y desactivar hooks concretos; revocar credencial relay;
desactivar receptor sin borrar el buzón ni recibos; retirar cambios de acceso
privado si se hubieran aprobado. Detener units PM/worker por su nombre exacto, sin
eliminar datos, revocar identidad equivocada ni habilitar integrador como salida.

**Pruebas de transporte:** HMAC inválido; cuerpo/UUID/repositorio incorrectos;
duplicado/conflicto; caída entre persistencia y ack; host apagado y recuperación;
cuota agotada; rotación; relay comprometido; identidad App equivocada con HMAC
válido; discrepancia entre GitHub y relay; laguna histórica. Ejecutar prueba real
W2 con Apps separadas antes de declarar B-2 completo.

**Prueba funcional prioritaria:** conversación → objetivo confirmado → tareas
dependientes → asignación PM → dos ejecuciones reales autorizadas → fallo
recuperable → revisión/evidencia → consolidación → conversación original y vistas
LIVE; reiniciar un componente sin duplicar. CI, fixtures y scripts instalables no
sustituyen esta demostración. No se ha demostrado completa aún.
