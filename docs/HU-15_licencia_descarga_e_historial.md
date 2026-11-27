# [HU-15] Licencia, descarga e historial

**Módulo:** Comercio · **Submódulos:** SUB-17 (Licencias), SUB-18 (Descargas), SUB-19 (Historial de compras)
**Funciones:** FUN-44, FUN-45, FUN-46, FUN-47 · **Procesos:** PRC-44, PRC-45, PRC-46, PRC-47
**Actor:** Consumidor · **Prioridad:** Alta · **Puntos:** 8

> Estado: historia implementada. Los endpoints, la firma de la URL, la auditoría
> de descargas y sus pruebas se incorporan en esta rama.

### Historia de usuario

**Dado** un consumidor con una compra pagada,
**Para** que acceda a su producto digital y consulte sus compras cuando lo necesite,
**Que** reciba una licencia de uso, descargue el archivo y consulte su historial.

**Beneficio esperado:** el comprador obtiene acceso inmediato y seguro, y la
plataforma controla la distribución del contenido.

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-44 | Comercio | Licencias | Emitir licencia de uso | PRC-44 |
| FUN-45 | Comercio | Licencias | Consultar licencia | PRC-45 |
| FUN-46 | Comercio | Descargas | Descargar producto | PRC-46 |
| FUN-47 | Comercio | Historial de compras | Consultar historial de compras | PRC-47 |

## Flujo esperado

1. El pago confirmado (FUN-43) genera una licencia de uso, sin edición ni reventa.
2. El consumidor consulta la licencia y sus condiciones (FUN-45).
3. Solicita la descarga (FUN-46) y el sistema valida que la licencia esté activa.
4. Se genera una URL firmada y de expiración corta para el archivo del producto.
5. El consumidor consulta su historial de compras y licencias (FUN-47).

## Endpoints

Todas las respuestas usan el sobre `{ message, data, success }`.

| FUN | Método | Ruta | Resultado |
|---|---|---|---|
| FUN-45 | `GET` | `/api/v1/commerce/licenses/{id}` | `200` con licencia; `401`/`403`/`404` |
| FUN-46 | `GET` | `/api/v1/commerce/purchases/{id}/download` | `200` con URL firmada; `401`/`403`/`404` |
| FUN-47 | `GET` | `/api/v1/commerce/purchases` | `200` paginado; `400`/`401` |
| FUN-46 | `GET` | `/api/v1/commerce/downloads/{token}` | Acceso a la URL firmada: `307` a S3; `403`/`410` |

### Autorización y origen del comprador

- Se reutiliza el resolvedor de actor de la API: `Authorization: Bearer <token>`
  o, mientras se integra la autenticación, `X-Actor-Id` / `X-Actor-Roles`,
  igual que HU-03 a HU-14.
- Toda operación requiere consumidor autenticado (`401 CONSUMER_REQUIRED`).
- El `compradorId` siempre se deriva del actor autenticado; nunca se toma del
  cuerpo o de la query. Una licencia o compra de otro usuario responde `403`
  (o `404` para no revelar su existencia).

### Emisión de la licencia (FUN-44)

- Solo se emite para una orden en estado `pagada`. Una orden pendiente,
  cancelada o rechazada nunca genera licencia.
- La emisión ocurre en la misma transacción lógica de la confirmación del pago:
  no hay segundo cobro ni acción del comprador. Si la emisión falla después del
  commit del pago (convención de HU-14), se reintenta de forma idempotente sin
  cobrar de nuevo.
- Una orden pagada produce **una sola** licencia: un `eventId` repetido o un
  reintento no duplica el registro.
- Condiciones fijas: **uso personal, sin edición ni reventa**. No se exponen
  condiciones configurables por el comprador.
- Formato `lic_NNN` y tabla `licencias`, reutilizando el contrato creado en HU-08
  y ampliado con `actor_id` en HU-10. HU-14 ya consume este contrato, por lo que
  no se define un segundo registro de propiedad.

### GET `/api/v1/commerce/licenses/{id}` (FUN-45)

Devuelve el estado (`activa` cuando la licencia está vigente) y las condiciones.
La licencia contiene `id`, `productoId`, `compradorId`, `estado`, `condiciones` y
`fechaEmision`.

```json
{
  "message": "Licencia consultada correctamente.",
  "data": {
    "id": "lic_900",
    "productoId": "prod_100",
    "compradorId": "usr_001",
    "estado": "activa",
    "condiciones": "Uso personal, sin edición ni reventa",
    "fechaEmision": "2026-10-25T18:05:00Z"
  },
  "success": true
}
```

### GET `/api/v1/commerce/purchases/{id}/download` (FUN-46)

Requiere una licencia **activa** del comprador para el producto de la compra.
Sin licencia vigente responde `403 LICENSE_REQUIRED`; una compra inexistente
responde `404 PURCHASE_NOT_FOUND`.

La respuesta contiene `url`, `expiraEn` y `nombreArchivo`:

```json
{
  "message": "Descarga autorizada correctamente.",
  "data": {
    "url": "http://localhost:8000/api/v1/commerce/downloads/eyJrIjoicHJvZF8xMDAvcGFjay53ZWItLi4ifQ.ofnC0A...",
    "expiraEn": "2026-10-25T18:15:00Z",
    "nombreArchivo": "pack-de-ilustraciones.webp"
  },
  "success": true
}
```

- Un producto **archivado** conserva el acceso: la validación se apoya en la
  licencia vigente, no en que el producto siga publicado en la vitrina (HU-08 no
  altera las licencias al archivar).
- El límite de descargas se resuelve desde COM-09. Al alcanzarlo responde
  `403 DOWNLOAD_LIMIT_REACHED`; el contador se incrementa de forma atómica solo
  cuando se autoriza la descarga.
- Cada autorización queda auditada con `actorId`, `productoId`, `licenciaId`, IP
  de origen y fecha. No se persiste la URL firmada en la auditoría.

### URL firmada y vencimiento

- La URL se genera con una firma HMAC-SHA256 sobre una carga canónica que
  incluye la clave del objeto, la licencia y `expiraEn`, con secreto de Comercio.
  La comparación de la firma en el acceso es de tiempo constante.
- `expiraEn` se calcula como `fechaActual + COM-08` minutos. El valor se lee de
  la configuración vigente de Comercio en cada solicitud
  (`COM_08_DOWNLOAD_TTL_MINUTES`, 10 por defecto); **no** se fija una constante
  en el código. Una vez vencida, la URL responde `410 URL_EXPIRED`.
- La URL devuelta apunta a `GET /api/v1/commerce/downloads/{token}`. Ese endpoint
  valida firma y vencimiento y redirige (`307`) al objeto de S3 configurado en
  `COMMERCE_STORAGE_BASE_URL`; los objetos no son públicos y el acceso queda
  acotado por la firma y el tiempo. Una firma alterada responde `403`.
- COM-09 (`COM_09_MAX_DOWNLOADS`, 3 por defecto) se comprueba de forma atómica
  antes de autorizar cada descarga.
- El nombre del archivo se deriva del producto y se normaliza para evitar rutas
  relativas o caracteres peligrosos.

### GET `/api/v1/commerce/purchases` (FUN-47)

Devuelve únicamente las compras del actor autenticado, paginadas y ordenadas por
fecha (más reciente primero por defecto). Parámetros: `pagina` (desde 1) y
`tamanioPagina` (entre 1 y el tope configurado); valores inválidos responden
`400 PAGINATION_INVALID`.

```json
{
  "message": "Historial de compras consultado correctamente.",
  "data": {
    "compras": [
      {
        "id": "ord_500",
        "productoId": "prod_100",
        "estado": "pagada",
        "fechaCompra": "2026-10-25T18:05:00Z",
        "licenciaId": "lic_900",
        "estadoLicencia": "activa"
      }
    ],
    "licencias": [
      {
        "id": "lic_900",
        "productoId": "prod_100",
        "estado": "activa",
        "condiciones": "Uso personal, sin edición ni reventa"
      }
    ],
    "pagina": 1,
    "tamanioPagina": 20,
    "total": 1,
    "totalPaginas": 1
  },
  "success": true
}
```

El historial incluye compras, licencias y estados. Las compras ajenas no se
listan ni se filtran mediante parámetros de usuario.

## Errores

| Situación | HTTP | `data.codigo` |
|---|---|---|
| Sin actor autenticado | 401 | `CONSUMER_REQUIRED` |
| Licencia inexistente | 404 | `LICENSE_NOT_FOUND` |
| Licencia/compra de otro usuario | 403 o 404 | `FORBIDDEN` / `NOT_FOUND` |
| Descarga sin licencia activa | 403 | `LICENSE_REQUIRED` |
| Límite COM-09 agotado | 403 | `DOWNLOAD_LIMIT_REACHED` |
| URL con firma inválida | 403 | `SIGNATURE_INVALID` |
| URL vencida (más de COM-08 minutos) | 403 o 410 | `URL_EXPIRED` |
| Compra inexistente | 404 | `PURCHASE_NOT_FOUND` |
| Paginación inválida | 400 | `PAGINATION_INVALID` |

Ninguna respuesta de error emite licencia, incrementa el contador de descargas
ni publica eventos.

## Decisiones técnicas y límites con otros módulos

1. **Origen de la licencia:** HU-14 confirma el pago y emite la licencia sobre la
   tabla `licencias` existente; HU-15 solo la consulta y la valida. La licencia
   se emite para una orden pagada y nunca para una orden cancelada o pendiente.
2. **Condiciones:** uso personal, sin edición ni reventa. El archivo se entrega
   tal cual; la licencia no habilita transformación ni redistribución.
3. **Archivado:** HU-08 garantiza que archivar un producto no modifica sus
   licencias. La descarga con licencia vigente sigue disponible aunque el
   producto ya no figure en la vitrina.
4. **Parámetros:** COM-08 (minutos de vigencia de la URL) y COM-09 (límite de
   descargas) pertenecen a Comercio y se resuelven desde la configuración
   vigente; HU-13 y HU-21 rechazan el prefijo `COM-`, por lo que no hay
   solapamiento de parámetros ni de alcances.
5. **Auditoría:** se registra quién descarga qué producto, desde qué IP y cuándo.
   La URL firmada no se expone en logs; el evento de auditoría usa el mismo
   patrón de `AuditEvent` de HU-11/HU-14.
6. **Historial:** se consulta solo con el actor autenticado; la fecha de la
   compra y el estado de la licencia se derivan de los registros de orden y
   licencia, sin duplicar un estado propio.

## Criterios de aceptación

- [x] La licencia se emite solo para una orden pagada.
- [x] La licencia permite uso sin edición y no permite reventa.
- [x] `GET /licenses/{id}` devuelve estado y condiciones.
- [x] `GET /purchases/{id}/download` exige licencia activa.
- [x] La URL de descarga vence en COM-08 minutos.
- [x] El límite de descargas respeta COM-09.
- [x] Un producto archivado sigue disponible para licencias vigentes.
- [x] `GET /purchases` pagina y ordena por fecha.
- [x] La licencia contiene id, productoId, compradorId, estado, condiciones y fecha.
- [x] La descarga devuelve url, expiraEn y nombreArchivo.
- [x] El historial contiene compras, licencias y estados.

## Casos de prueba previstos

1. **Consultar licencia:** compra pagada → `GET /licenses/{id}` → `200` con
   licencia activa y sus condiciones.
2. **Descarga con licencia:** licencia activa → `GET /download` → `200` con URL
   firmada, `expiraEn` y `nombreArchivo`.
3. **Descarga sin licencia:** usuario sin compra → `GET /download` → `403`.
4. **URL expirada:** URL con más de COM-08 minutos → `410 URL_EXPIRED`.
5. **Historial:** compras pagadas → `GET /purchases` → `200` paginado y ordenado
   por fecha.
6. **Producto archivado:** licencia vigente y producto archivado → descarga →
   `200`, acceso conservado.

## Definición de hecho

- [x] Licencia, descarga e historial documentados.
- [x] URL firmada y expiración probadas.
- [x] Control de acceso verificado.
- [x] Auditoría de descargas activa.
- [x] Licencias conservadas al archivar.

## Pruebas

```bash
pytest -q tests/test_commerce_domain.py tests/test_commerce_api.py
pytest -q
```

`test_commerce_domain.py` cubre la firma HMAC, la alteración del token, el
vencimiento y la paginación. `test_commerce_api.py` cubre los seis casos de
aceptación, además de la emisión idempotente solo para órdenes pagadas, el
límite COM-09 y el registro de auditoría con IP. La suite completa pasa con
207 pruebas.
