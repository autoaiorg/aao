# Servicio persistente del worker Codex de Self Development

## Alcance y estado

`deploy/systemd/user/aao-selfdev-codex-worker.service` es una plantilla opcional
para un worker de cola bajo la cuenta Linux `aao-impl-codex`. No se instala,
habilita ni inicia con este cambio. La unidad falla cerrada si no existen su
archivo de activación y el token runtime del rol.

El worker obtiene el `principal_id` llamando a `GET /v1/principals/me` con el
token privado del ciclo y acepta únicamente un principal AGENT habilitado cuyo
ID empieza por `aao-selfdev-impl-`. Así no se fija en la unidad un ID de ciclo
que cambia en cada emisión. Si se configura además `AAO_WORKER_PRINCIPAL_ID`, se
exige que coincida exactamente con el principal autenticado.

## Contrato y límites

- Se usa el árbol congelado y el venv de `/srv/aao/frozen/aao-pm`, que es el
  par que actualmente reconoce `pm_deployment_preflight.py` como código runtime
  congelado. Antes de habilitarlo, verificar que ambos están en la revisión
  aprobada y que incluyen esta versión del worker.
- El token se lee desde `${XDG_RUNTIME_DIR}/aao-self-development-agent.token`
  con controles de propietario y modo 0600. La unidad no lo copia ni imprime.
- `CODEX_HOME` es la identidad autenticada dedicada de `aao-impl-codex`:
  `/home/aao-impl-codex/.local/share/aao/codex-agent`. No debe apuntar al home
  de otra cuenta. El modelo solo ve ese home dentro del jail previsto por
  `agent_runner`; no se monta el token AAO del host.
- El worker solo consume ejecuciones que la API ya dejó encoladas. La unidad no
  crea tareas, no otorga grants y no hace staging por sí misma.
- La API debe tener `AAO_AGENT_PROVIDER=codex` para staging de capacidades
  Codex; el worker necesita esa misma activación y el `CODEX_HOME` dedicado.
  Esto es independiente de la unidad. La plantilla no configura el proveedor
  por defecto.
- La API configurada por `AAO_API_BASE_URL` debe ser loopback en este despliegue.
- La autenticación de Codex puede expirar o ser revocada; este documento no
  comprueba ni renueva credenciales de OpenAI.

## Bloqueo de autonomía del ciclo

Las identidades Self Development son por ciclo y expiran en un máximo de dos
horas. `request_selfdev_cycle_roles.py` comprueba que los ficheros de rol estén
vacíos antes de emitirlos, y el instalador no sobrescribe un fichero existente.
No existe en este cambio una operación segura de ciclo completo que pare el
worker, retire/revoque los dos roles anteriores, emita el siguiente par,
instale/verifique ambos tokens, revalide el candidato y reanude el worker. Por
tanto esta unidad **no constituye todavía operación autónoma persistente**: su
modo `--watch` es persistente solo mientras siga válido el token del ciclo.
No se debe ocultar el bloqueo con una credencial estática ni con reintentos
indefinidos.

Para cerrar el lifecycle hace falta una interfaz supervisada que permita al PM
rotar exactamente el ciclo Self Development, con garantías de que:

1. cada ciclo conserva su principal implementador/revisor propio y su TTL;
2. el trabajador se detiene antes de reemplazar su token y reanuda solo tras
   verificar el token nuevo y `GET /v1/principals/me`;
3. fallos parciales revocan los principals nuevos y no dejan credenciales
   ambiguas; los tokens antiguos nunca se muestran en logs;
4. la API vuelve a comprobar grants, proyecto, estado de tarea, límites de
   intentos, presupuesto y provider activation al hacer staging/claim;
5. el revisor permanece separado y ningún resultado se autoaprueba, publica o
   fusiona.

## Preparación opt-in (no ejecutada)

La configuración de activación debe vivir en
`/etc/aao/selfdev-codex-worker.env`, root-owned y legible por
`aao-impl-codex` (modo 0644: contiene solo la selección del proveedor y una
ruta no secreta; no contiene tokens):

```ini
AAO_AGENT_PROVIDER=codex
AAO_AGENT_CODEX_HOME=/home/aao-impl-codex/.local/share/aao/codex-agent
```

La instancia del servicio es el UUID del proyecto (por ejemplo
`aao-selfdev-codex-worker@9d17d6c1-d644-424a-a425-fe7e084c3d91.service`). La
unidad fija la API a `http://127.0.0.1:8001` y el entorno a `production`; no
carga `.env.local`.

No se proporciona fichero instalado ni se ejecuta `systemctl enable/start`.
Antes de preparar el fichero, confirmar que la API tiene la activación requerida
y que una tarea de prueba está explícitamente admitida. Asegurar también que
`codex` está disponible por el `PATH` limpio del jail (`/usr/local/bin:/usr/bin:/bin`)
y que su directorio de release puede leerse por la cuenta del rol.

El despliegue tendría estos pasos administrados, después de validar el lifecycle
de ciclo anterior:

1. Instalar la unidad en
   `/home/aao-impl-codex/.config/systemd/user/` propiedad de
   `aao-impl-codex`, modo 0644; configuración separada y privada.
2. `sudo -u aao-impl-codex -H env XDG_RUNTIME_DIR=/run/user/1002 systemctl --user daemon-reload`.
3. Revisar `systemd-analyze --user verify` y preflight como el rol.
4. Solo para un ensayo delimitado: iniciar la unidad y monitorizar el ciclo,
   tokens, resultado y parada; no hacer enable permanente antes de disponer del
   lifecycle automático y su procedimiento de recuperación.

Las órdenes anteriores son guía futura. Ninguna fue ejecutada en la creación de
este artefacto.
