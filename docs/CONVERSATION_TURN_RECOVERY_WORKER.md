# Recuperación backend de turnos de conversación

`scripts/run_conversation_recovery_worker.py` procesa, como máximo, un turno persistido por iteración. Solo reclama turnos `PENDING` con lease vencida (o sin lease), proyecto activo y `provider`/`model` iguales a la configuración del worker. La reclamación usa PostgreSQL `FOR UPDATE SKIP LOCKED` y actualización condicional; heartbeat, éxito y fallo quedan cercados por el propietario de lease. La respuesta y el estado del turno se confirman en una transacción y se anotan en el ledger de eventos.

El worker es **opt-in**. Sin `AAO_CONVERSATION_RECOVERY_ENABLED=true`, retorna `DISABLED` antes de conectar a PostgreSQL. Además requiere:

- `AAO_CONVERSATION_PROVIDER=openai-compatible`;
- `AAO_CONVERSATION_MODEL` coincidente con el modelo registrado en el turno;
- `AAO_CONVERSATION_API_URL` y `AAO_CONVERSATION_API_KEY` configurados.

La configuración del proveedor debe inyectarse por el supervisor de servicio autorizado; el script no acepta secretos en argumentos y nunca imprime valores de configuración. La conexión PostgreSQL reutiliza la configuración central de AAO, que puede cargar `.env.local` en entornos locales de desarrollo/prueba y no la carga en producción. Un turno vencido que pertenece a otro proveedor/modelo permanece intacto y devuelve `CONFIGURATION_MISMATCH`; debe ejecutarse con la configuración coincidente para recuperarlo. La configuración faltante tampoco modifica filas.

## Ejecución controlada

Una vez que el CEO haya autorizado el proveedor/modelo para el entorno y que el operador haya habilitado explícitamente el worker:

```sh
python scripts/run_conversation_recovery_worker.py --once
python scripts/run_conversation_recovery_worker.py --watch --poll-seconds 5
```

No se ha desplegado ni activado este worker como parte del cambio de código. La comprobación automatizada de integración debe usar una base PostgreSQL desechable y cubrir dos workers concurrentes, lease vencida/no vencida, fencing ante pérdida de lease, persistencia/auditoría de éxito y fallo. No existe garantía de evitar una segunda llamada/coste externo si el proveedor respondió y el proceso murió antes de persistir: el fence evita duplicar el resultado AAO local, pero no sustituye una clave de idempotencia soportada por el proveedor.
