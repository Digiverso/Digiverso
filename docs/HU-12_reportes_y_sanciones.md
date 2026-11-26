# [HU-12] Reportes y sanciones — implementación

**Módulo:** Catálogo · **Submódulo:** SUB-13 · **Funciones:** FUN-35, FUN-36, FUN-37
**Actor:** Consumidor, Productor, Administrador · **Prioridad:** Media · **Puntos:** 5

### Historia de usuario

**Dado** un usuario que detecta contenido que incumple las políticas,
**Para** que la plataforma investigue y aplique una medida proporcional,
**Que** reporte el contenido con evidencia y el administrador gestione el reporte y la sanción.

| FUN | Proceso | Funcionalidad |
|---|---|---|
| FUN-35 | PRC-35 | Reportar contenido |
| FUN-36 | PRC-36 | Gestionar reporte |
| FUN-37 | PRC-37 | Aplicar sanción |

## Endpoints

Todas las respuestas usan el sobre `{ message, data, success }`. Reportar
requiere un actor autenticado (sesión RS256, token de actor o `X-Actor-Id` y
`X-Actor-Roles`). Consultar reportes, resolverlos y sancionar requiere rol
`administrador` o el alcance `catalog.reports.write`.

| FUN | Método | Ruta | Resultado |
|---|---|---|---|
| FUN-35 | `POST` | `/api/v1/catalog/reports` | `201`, reporte `abierto` |
| FUN-36 | `GET` | `/api/v1/catalog/publication-control/reports` | `200`, cola filtrable |
| FUN-36 | `GET` | `/api/v1/catalog/publication-control/reports/{id}` | `200` / `404` |
| FUN-36 | `PATCH` | `/api/v1/catalog/publication-control/reports/{id}` | `200`, resolución |
| FUN-37 | `POST` | `/api/v1/catalog/publication-control/sanctions` | `201`, sanción CAT-15 |
| FUN-37 | `GET` | `/api/v1/catalog/publication-control/sanctions` | `200`, histórico |

### POST `/api/v1/catalog/reports` (FUN-35)

Exige `contenidoId`, `motivo` de CAT-14 y `evidencia` no vacía. El tipo de
contenido se infiere del identificador (`prod_` → producto, `res_` → reseña,
`usr_` → usuario) o se declara en `tipoContenido`.

```json
{
  "contenidoId": "prod_100",
  "motivo": "derechos_autor",
  "evidencia": "Captura del archivo original sin licencia.",
  "tipoContenido": "producto"
}
```

Motivos aceptados (CAT-14): `derechos_autor`, `contenido_inseguro`, `acoso`,
`spam`, `fraude`, `informacion_falsa`, `edad_inadecuada`,
`autoria_no_verificada`, `derechos_no_aclarados`, `funciones_no_verificadas`,
`violencia`, `discriminacion`, `cat-14` y `otro` (este último con observación).
Se aceptan variantes con guiones y mayúsculas.

```json
{
  "message": "Reporte registrado correctamente.",
  "data": {
    "id": "rep_010",
    "contenidoId": "prod_100",
    "motivo": "derechos_autor",
    "evidencia": "Captura del archivo original sin licencia.",
    "estado": "abierto",
    "fecha": "2026-10-25T18:00:00Z"
  },
  "success": true
}
```

La respuesta nunca incluye `reportanteId`: la identidad de quien reporta solo
queda en la fila privada del reporte y en la auditoría interna. La evidencia se
guarda como JSON en columnas de acceso interno y solo se devuelve al propio
reportante o al administrador a través de endpoints autenticados.

### GET `/publication-control/reports` (FUN-36)

Filtros opcionales: `estado`, `contenidoId`, `motivo`, `pagina`,
`tamanioPagina`. Devuelve la cola ordenada por fecha descendente.

```json
{
  "message": "Reportes consultados correctamente.",
  "data": {
    "items": [{
      "id": "rep_010",
      "contenidoId": "prod_100",
      "motivo": "derechos_autor",
      "evidencia": "Captura del archivo original sin licencia.",
      "estado": "abierto",
      "fecha": "2026-10-25T18:00:00Z"
    }],
    "total": 1,
    "pagina": 1,
    "tamanioPagina": 20
  },
  "success": true
}
```

### PATCH `/publication-control/reports/{id}` (FUN-36)

La decisión puede ser `desestimar` o `sancionar` (se aceptan `desestimado`,
`sin_accion`, `sancion`, `aplicar_sancion` y equivalentes). La resolución
contiene `decision`, `sancion` y `observacion`.

```json
{
  "decision": "sancionar",
  "observacion": "Se confirma el uso no autorizado.",
  "sancion": {
    "tipo": "suspension_temporal",
    "duracionDias": 15,
    "usuarioAfectado": "usr_010"
  }
}
```

```json
{
  "message": "Reporte resuelto correctamente.",
  "data": {
    "id": "rep_010",
    "contenidoId": "prod_100",
    "motivo": "derechos_autor",
    "evidencia": "Captura del archivo original sin licencia.",
    "estado": "resuelto",
    "fecha": "2026-10-25T18:00:00Z",
    "resolucion": {
      "decision": "sancionado",
      "sancion": "san_001",
      "observacion": "Se confirma el uso no autorizado.",
      "fecha": "2026-10-26T09:00:00Z"
    },
    "decision": "sancionado",
    "sancion": "san_001",
    "observacion": "Se confirma el uso no autorizado."
  },
  "success": true
}
```

### POST `/publication-control/sanctions` (FUN-37)

Tipos permitidos por CAT-15:

| Tipo | Significado | Acción sobre el contenido |
|---|---|---|
| `advertencia` | Llamado de atención formal | Restringir |
| `restriccion_contenido` | Limita la visibilidad del contenido | Restringir |
| `suspension_temporal` | Suspende al usuario por días (CAT-16) | Archivar |
| `bloqueo_permanente` | Retira al usuario y su contenido | Archivar |

```json
{
  "reporteId": "rep_010",
  "tipo": "suspension_temporal",
  "duracionDias": 15,
  "usuarioAfectado": "usr_010",
  "motivo": "derechos_autor",
  "observacion": "Uso no autorizado de ilustraciones."
}
```

```json
{
  "message": "Sanción aplicada correctamente.",
  "data": {
    "id": "san_001",
    "reporteId": "rep_010",
    "contenidoId": "prod_100",
    "tipo": "suspension_temporal",
    "duracionDias": 15,
    "usuarioAfectado": "usr_010",
    "fecha": "2026-10-26T09:00:00Z",
    "politica": "CAT-15",
    "accionContenido": "archivar",
    "estadoContenido": "archivado",
    "apelable": true,
    "notificado": true
  },
  "success": true
}
```

Si se omite `duracionDias` en una suspensión se aplica el valor de CAT-16
(`report_suspension_days`, 7 días por defecto, configurable con
`CAT_16_SUSPENSION_DAYS`). El usuario afectado se infiere del producto o del
identificador `usr_` cuando no se envía explícitamente. La sanción se registra
con la evidencia del reporte, marca el reporte como `resuelto` y deja constancia
del canal de apelación en la notificación.

## Reglas y errores

| Regla | Código | Resultado |
|---|---|---|
| Motivo fuera de CAT-14 | `REPORT_REASON_INVALID` | `400` |
| Evidencia ausente o vacía | `REPORT_EVIDENCE_REQUIRED` | `400` |
| Decisión desconocida | `REPORT_DECISION_INVALID` | `400` |
| Tipo de sanción fuera de CAT-15 | `SANCTION_TYPE_INVALID` | `400` |
| Duración CAT-16 inválida | `SANCTION_DURATION_INVALID` | `400` |
| Reporte abierto duplicado | `REPORT_DUPLICATE` | `409` |
| Reporte ya resuelto | `REPORT_INVALID_STATE` | `409` |
| Reporte inexistente | `REPORT_NOT_FOUND` | `404` |
| Actor no administrador | `REPORT_FORBIDDEN` | `403` |

## Eventos y notificaciones

Se publican en `app.state.event_bus`:

| Tema | Momento |
|---|---|
| `report.created` | FUN-35 confirma el reporte en la cola de control |
| `report.resolved` | FUN-36 registra desestimación o sanción |
| `sanction.applied` | FUN-37 confirma la medida y la acción sobre el contenido |

Después del commit se envían `reporte_recibido` al reportante,
`reporte_resuelto` al reportante y `sancion_aplicada` al usuario afectado.
Los textos incluyen el motivo CAT-14, la decisión y, cuando aplica, los días de
CAT-16 y la vía de apelación. Un fallo de entrega no revierte la decisión; el
campo `notificado` de la sanción refleja el resultado.

## Decisiones técnicas

- **Persistencia:** tablas `reportes` y `sanciones` en SQLite. Un índice único
  parcial sobre `(reportante_id, contenido_id)` donde `estado IN ('abierto',
  'en_revision')` garantiza la regla de duplicados incluso en concurrencia.
- **Evidencia restringida:** se almacena como JSON con una huella SHA-256 en
  `evidencia_hash`; la auditoría guarda la huella y la evidencia, sin exponer
  rutas privadas ni la identidad del reportante en las respuestas.
- **Contenido sancionado:** si el contenido es un producto, se archiva
  (`estado = 'archivado'`, `activo = 0`) o se restringe (`activo = 0`) según la
  medida; se actualiza el índice de búsqueda y se invalida la caché de vitrina.
- **Auditoría:** `crear_reporte`, `resolver_reporte`, `aplicar_sancion` y
  `sancionar_contenido` quedan en `audit_log` con actor, fecha, motivo y
  evidencia.
- **Reutilización:** el bus de eventos y el servicio de notificaciones se
  comparten con el control de publicaciones (HU-11) cuando está instalado.

## Pruebas

```bash
pytest -q
```

`tests/test_reports_api.py` cubre los cinco casos de aceptación (reporte válido,
motivo inválido, duplicado, suspensión CAT-16 y desestimación), además del
acceso por roles, el filtrado de la cola, la apelación en la notificación, la
auditoría de decisiones y el archivo del producto sancionado.
