# Protocolo de emisión mTLS para ciclos Self Development

Estado: **contrato y reconciliador de referencia; no hay firmante de
producción ni emisión mTLS de ciclos operativa.** La emisión bearer del endpoint
de ciclo se rechaza en `AAO_ENV=production` hasta que se integre el flujo
completo. El contrato no autoriza crear una CA ni desplegar servicios.

## Límites de confianza

- El workload genera su clave privada localmente y conserva el fichero modo
  `0600`. La clave nunca cruza la API, el socket, argumentos, entorno ni logs.
- La API crea la intención tipada solo después de confirmar en una transacción
  el ciclo, principal fijo, tipo de workload, grants y vencimiento. El cliente
  no puede elegir sujeto, propósito, grants ni `not_after`.
- El firmante dedicado recibe únicamente una intención de ciclo ya persistida y
  el CSR público. No existe operación de firma CSR genérica. El firmante vuelve
  a leer el registro comprometido, comprueba que el ciclo y el principal sigan
  pendientes/no revocados, valida el UID del peer y que ese UID corresponde al
  principal exacto, y emite solo SAN/purpose fijados por el protocolo.
- Implementador (`AGENT`) y revisor (`AUDITOR`) son identidades separadas por
  ciclo. El certificado tiene validez máxima igual al vencimiento de ciclo
  (actualmente hasta 2 h). La revocación de DB prevalece inmediatamente sobre
  una conexión TLS ya abierta.
- El certificado no ejecuta autoridad por sí solo: el principal permanece
  deshabilitado/no ejecutable hasta que el verificador valide cadena, SAN,
  clave pública CSR-cert, ventana temporal y huella, y la DB inserte el binding
  y habilite ese principal atómicamente.

## Contrato local del firmante

El firmante se invoca sobre un socket Unix con autorización del UID del peer;
no expone un listener TCP ni acepta un CSR sin intención. El protocolo de
referencia es una petición JSON de una sola línea, con límite estricto de 64 KiB
para CSR y 4 KiB para cabecera:

```json
{"version":1,"operation":"issue_selfdev_cycle_certificate",
 "intent_id":"<uuid>","cycle_id":"<32 lowercase hex>",
 "principal_id":"aao-selfdev-impl-<cycle id>","kind":"AGENT",
 "csr_pem":"<public CSR PEM>"}
```

`principal_id`, `cycle_id` y `kind` son identificadores para localizar la
intención, no autoridad del solicitante. El firmante compara todos ellos con
DB y el UID del peer; ignora/rechaza cualquier campo adicional, grants, expiry,
subject/SAN, extensión o algoritmo escogido por cliente. `not_before` y
`not_after` salen exclusivamente de la intención persistida. Un identificador
revisor solo se admite con el prefijo fijo `aao-selfdev-review-` y tipo
`AUDITOR`. La respuesta es exclusivamente cadena PEM pública y fingerprint; no
incluye key ni bearer. Repetir la misma intención y mismo CSR devuelve el mismo
certificado/fingerprint; mismo intent con CSR distinto produce conflicto y
requiere revocar el intent antes de reemplazarlo. El cliente no reintenta con
otro intent por su cuenta.

Este documento define el protocolo de aplicación, no el detalle del transporte
real, permisos del socket, formato del almacén ni custodia de CA. Esa selección
requiere revisión independiente y una decisión de despliegue; no se implementa
ni se simula como producción aquí.

## Reconciliación requerida

`src/aao/selfdev_cycle_mtls.py` define la lógica sin acoplarla a una custodia:

1. Carga una intención pendiente autoritativa desde el repositorio.
2. Si ya se completó, compara SHA-256 del CSR recibido con el digest persistido.
   Devuelve la huella solo si coincide exactamente; CSR distinto es conflicto y
   no vuelve a firmar.
3. Pasa CSR público y la intención tipada a `CycleSigner`.
4. Pasa certificado/cadena por `CertificateVerifier`, que debe comprobar
   firma de CSR, cadena de confianza, SAN exacto, EKU de cliente, vigencia y
   huella SHA-256.
5. Solo después llama `complete_binding`, cuya implementación debe bloquear
   intent y principal, revalidar no revocado/no vencido, y en una única
   transacción insertar el binding mTLS y habilitar el principal.

Un error en cualquier etapa deja al principal no ejecutable. Los errores
externos se redaccionan: no incluyen CSR, certificado, clave ni mensajes del
firmante. No se registran cuerpos de protocolo. La idempotencia y atomicidad de
DB son obligaciones del adaptador `IntentRepository`; no se consideran
implementadas hasta que exista migración, repositorio SQL y pruebas concurrentes
contra PostgreSQL.

## Rotación, revocación y recuperación

- Crear la nueva identidad y su intent no revoca el ciclo anterior. La rotación
  usa el overlap acotado definido en
  `SELFDEV_CYCLE_CREDENTIAL_LIFECYCLE.md`; no se permite resolver la identidad
  por UID Linux genérico.
- Si el CSR se pierde antes de firmar, se puede volver a generar solo para la
  intención pendiente; el firmante fija un CSR por intent una vez emitido.
- Si el proceso cae después de emitir y antes de confirmar en DB, la repetición
  recupera el mismo certificado desde el firmante idempotente, verifica y
  completa el binding. Si el intent fue revocado o expiró, no se completa.
- Revoke debe deshabilitar principal y binding dentro de la misma transacción
  que invalida el ciclo; repetición es no-op seguro. Certificados vencidos o
  revocados no pueden revivir por reintento.
- No hay fallback bearer en producción. Hasta que exista el adaptador SQL, el
  firmante/socket revisado, y pruebas de integración/disposable host, el endpoint
  de ciclo responde 503 en producción.

## Decisiones y trabajo pendiente

1. **CEO/host administrator:** elegir custodia real (servicio dedicado root o
   mecanismo hardware) y custodio/rotación de la clave CA. No se toma aquí.
2. **API/DB owner:** migración de intenciones tipadas, estados y permisos
   mínimos; ciclo no ejecutable hasta completar binding; revocación y retención
   idempotentes bajo concurrencia.
3. **Host owner:** ACL socket para API y cada UID workload, store de certificados
   públicos, entrega privada de key/cert por `LoadCredential=` y recuperación
   de crash. Nada desplegado.
4. **GOV-REV-001:** auditoría independiente del protocolo, signer, esquema,
   reconciliador y suites adversariales antes de merge/activación.

## Evidencia de este PR

Los tests del reconciliador usan dobles en memoria; no crean CA ni certificados
reales. Demuestran el orden verify-before-bind, redacción de fallos, límites de
entrada e idempotencia de replay en el adaptador. No prueban PostgreSQL,
concurrencia real, socket, custodia CA, TLS en producción ni comportamiento del
host; el test de atomicidad usa un fake que modela un único registro persistido.
