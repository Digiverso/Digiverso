# [HU-11] Control de publicaciones — implementación

**Módulo:** Catálogo · **Submódulo:** SUB-13 · **Funciones:** FUN-32, FUN-33, FUN-34, FUN-38
**Actor:** Administrador · **Prioridad:** Alta · **Puntos:** 8

### Historia de usuario

**Dado** un administrador responsable de verificar el cumplimiento de las políticas,
**Para** que solo se publiquen productos propios, seguros y con derechos de autor claros,
**Que** consulte la cola de revisión, apruebe o rechace con justificación y notifique al productor.

| FUN | Proceso | Funcionalidad |
|---|---|---|
| FUN-32 | PRC-32 | Consultar cola de revisión |
| FUN-33 | PRC-33 | Aprobar publicación |
| FUN-34 | PRC-34 | Rechazar publicación |
| FUN-38 | PRC-38 | Notificar resultado de revisión |

## Endpoints

Todas las respuestas usan el sobre `{ message, data, success }`. Requieren un
administrador autenticado: sesión RS256 (`Authorization: Bearer <accessToken>`),
token de actor firmado o, mientras se integra la autenticación, `X-Actor-Id` y
`X-Actor-Roles: administrador`.

| FUN | Método | Ruta | Resultado |
|---|---|---|---|
| FUN-32 | `GET` | `/api/v1/catalog/publication-control/queue` | `200`, cola ordenada por antigüedad |
| FUN-33 | `PATCH` | `/api/v1/catalog/publication-control/{id}/approve` | `200`, `publicado` e indexado |
| FUN-34 | `PATCH` | `/api/v1/catalog/publication-control/{id}/reject` | `200`, `rechazado` con motivo |
| FUN-38 | evento | `product.reviewed` | Evento + notificación al productor |

### GET `/queue` (FUN-32)

Devuelve únicamente productos con `estado = 'en_revision'`, ordenados por
`fechaEnvio` ascendente (el más antiguo primero) y desempatados por `id`.
`fechaEnvio` es `estado_desde`, registrado por FUN-23 al enviar a revisión.

```json
{
  "message": "Cola de revisión consultada correctamente.",
  "data": {
    "total": 1,
    "items": [
      {
        "producto": {
          "id": "prod_001",
          "nombre": "Pack de ilustraciones",
          "estado": "en_revision",
          "autorId": "usr_010",
          "medios": [{ "id": "med_001", "tipo": "imagen", "url": "https://cdn.test/uno.webp", "orden": 0, "estado": "activo" }]
        },
        "autor": { "id": "usr_010", "nombre": "Ana Torres" },
        "fechaEnvio": "2026-10-25T17:30:00Z",
        "medios": [{ "id": "med_001", "tipo": "imagen", "url": "https://cdn.test/uno.webp", "orden": 0, "estado": "activo" }],
        "politicasAplicables": [
          { "codigo": "CAT-01", "descripcion": "Precio entero no negativo en COP." },
          { "codigo": "CAT-03", "descripcion": "Rango de edad apto para el contenido." },
          { "codigo": "CAT-09", "descripcion": "Imágenes mínimas declaradas por el productor." },
          { "codigo": "CAT-14", "descripcion": "Motivo de rechazo documentado con observación." }
        ]
      }
    ]
  },
  "success": true
}
```

### PATCH `/{id}/approve` (FUN-33)

Exige un checklist completo con las cinco verificaciones en `true`
(`autoria`, `edad`, `derechos`, `contenido`, `funciones`). Se aceptan alias como
`autoriaPropia`, `derechosDeAutor` o `contenidoSeguro` y una lista de nombres
marcados. Si falta alguna casilla, responde `400` sin cambiar el estado.

```json
{
  "checklist": {
    "autoria": true,
    "edad": true,
    "derechos": true,
    "contenido": true,
    "funciones": true
  }
}
```

```json
{
  "message": "Publicación aprobada correctamente.",
  "data": {
    "productoId": "prod_100",
    "estado": "publicado",
    "fechaPublicacion": "2026-10-25T18:00:00Z",
    "notificado": true
  },
  "success": true
}
```

### PATCH `/{id}/reject` (FUN-34)

Exige `motivo` (CAT-14) y `observacion`, ambos no vacíos. Se recomiendan estos
códigos, aunque se acepta cualquier motivo descriptivo:

| Motivo sugerido | Significado |
|---|---|
| `autoria_no_verificada` | No se acreditó la autoría del productor |
| `edad_inadecuada` | El contenido no es apto para el rango declarado |
| `derechos_no_aclarados` | Derechos de autor o licencias sin evidencia |
| `contenido_inseguro` | Contenido que incumple políticas de seguridad |
| `funciones_no_verificadas` | Funciones anunciadas que no se verificaron |
| `cat-14` | Motivo genérico de la política CAT-14 |
| `otro` | Otro motivo, siempre con observación |

```json
{
  "message": "Publicación rechazada correctamente.",
  "data": {
    "productoId": "prod_100",
    "estado": "rechazado",
    "motivo": "derechos_no_aclarados",
    "observacion": "Falta el permiso del ilustrador."
  },
  "success": true
}
```

El producto vuelve a `rechazado`, por lo que el productor puede corregirlo y
volver a enviarlo con FUN-23.

## Reglas y errores

| Regla | Código | Resultado |
|---|---|---|
| Actor sin rol administrador | `REVIEW_FORBIDDEN` | `403` |
| Administrador autor del producto | `REVIEW_SEPARATION_OF_DUTIES` | `403` |
| Checklist incompleto | `REVIEW_DECISION_INVALID` | `400` |
| Motivo CAT-14 ausente o vacío | `REVIEW_DECISION_INVALID` | `400` |
| Observación ausente | `REVIEW_DECISION_INVALID` | `400` |
| Producto inexistente | `PRODUCT_NOT_FOUND` | `404` |
| Producto que no está `en_revision` | `PRODUCT_INVALID_STATE` | `409` |

## Evento y notificación (FUN-38)

Tras confirmar el cambio de estado y la auditoría se publica
`product.reviewed` en el bus en memoria (`app.state.event_bus`):

```json
{
  "topic": "product.reviewed",
  "payload": {
    "productoId": "prod_100",
    "decision": "aprobado",
    "administradorId": "usr_admin",
    "fecha": "2026-10-25T18:00:00+00:00",
    "checklist": { "autoria": true, "edad": true, "derechos": true, "contenido": true, "funciones": true },
    "motivo": null,
    "observacion": null
  }
}
```

Después se envía la notificación al autor con los tipos `producto_publicado` o
`producto_rechazado` (AUT-10). El texto incluye la decisión y, en el rechazo, el
motivo CAT-14 y la observación. La entrega usa las preferencias del productor;
si falla, la decisión no se revierte y `notificado` es `false`.

## Decisiones técnicas

- **Persistencia:** no se añaden columnas. El checklist completo, el motivo, la
  observación, el contenido y su hash quedan en `audit_log.cambios` como
  evidencia inmutable de la decisión.
- **Índice:** `SQLiteProductRepository.update()` actualiza `productos_busqueda`,
  por lo que aprobar un producto lo hace visible de inmediato en la búsqueda;
  la caché de vitrina se invalida en la misma transición.
- **Orden:** `estado_desde` es la fecha de envío a revisión; la cola la ordena
  ascendente para atender primero lo más antiguo.
- **Separación de funciones:** se comprueba `producto.autor_id == actor.id`
  antes de cualquier transición, incluso si el actor tiene rol administrador.
- **Notificación después del commit:** `repository.update()` confirma el estado,
  luego se registra la auditoría, se publica el evento y se entrega la
  notificación. Un fallo de entrega no deshace la decisión.

## Pruebas

```bash
pytest -q
```

`tests/test_publication_control_api.py` cubre los cinco casos de aceptación:
aprobación con índice/evento/notificación/auditoría, rechazo sin motivo, acceso
no administrador, revisión de producto propio y notificación al productor.
Además verifica el orden de la cola, el checklist incompleto y el rechazo que
permite corregir y reenviar. La suite completa pasa con 172 pruebas.
