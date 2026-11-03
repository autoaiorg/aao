# Administrar bindings de identidad de workload

Este procedimiento requiere un administrador autorizado y una conexión PostgreSQL
administrativa separada de `aao_runtime`. El servicio API/runtime no debe crear ni
revocar bindings; nunca se eleva el rol runtime para resolver un fallo de identidad.

## Preparación administrativa

1. El DBA provisiona una conexión de mínimo privilegio para modificar solo
   `workload_identity_bindings` y escribir los eventos de auditoría requeridos.
   No usar la conexión superuser de inspección ni credenciales de `aao_runtime`.
2. En un host administrativo, guardar el DSN en un fichero regular, propiedad de
   root, modo `0600`, con una sola línea `postgresql://...`. No poner el DSN en
   argumentos, variables de entorno, historial, tickets ni logs. El fichero debe
   estar en una ruta local protegida y no ser un symlink.
3. Confirmar que `AAO_ENV=production` está fijado para la invocación, y ejecutar
   el CLI desde el árbol aprobado con Python/venv aprobado. El CLI requiere la
   ruta explícita `--admin-connection-file`; no lee el DSN runtime ni cae a
   `AAO_POSTGRES_URL`.

## Bind o revocación

Bind requiere un principal `AGENT` o `AUDITOR` ya existente, habilitado, y un
certificado cliente público cuyo fingerprint se haya verificado por el canal de
aprovisionamiento. La fecha de expiración debe incluir zona horaria y no superar
la expiración del principal.

```sh
sudo env AAO_ENV=production PYTHONPATH=/srv/aao/approved/tree/src \
  /srv/aao/approved/venv/bin/python \
  /srv/aao/approved/tree/scripts/manage_workload_identity_binding.py bind \
  --admin-connection-file /etc/aao/workload-identity-admin.dsn \
  --principal-id PRINCIPAL_ID \
  --certificate /secure/path/client-cert.pem \
  --expires-at 2026-11-03T23:00:00Z
```

Revocation usa el fingerprint SHA-256 DER del certificado y deja auditoría:

```sh
sudo env AAO_ENV=production PYTHONPATH=/srv/aao/approved/tree/src \
  /srv/aao/approved/venv/bin/python \
  /srv/aao/approved/tree/scripts/manage_workload_identity_binding.py revoke \
  --admin-connection-file /etc/aao/workload-identity-admin.dsn \
  --fingerprint-sha256 FINGERPRINT_SHA256
```

El comando no imprime el DSN. La credencial del fichero debe rotarse/eliminarse
por el DBA tras la operación. No ejecutar comandos de bind/revoke desde el API,
worker, ni como `aao_runtime`. La instalación de CA, emisión de certificados,
distribución de claves y rotación automática quedan fuera de este procedimiento.
