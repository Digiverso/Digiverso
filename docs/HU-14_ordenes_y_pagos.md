# [HU-14] Órdenes y pagos

**Módulo:** Comercio · **Submódulos:** SUB-15 (Órdenes), SUB-16 (Pagos)
**Funciones:** FUN-40, FUN-41, FUN-42, FUN-43 · **Procesos:** PRC-40, PRC-41, PRC-42, PRC-43
**Actor:** Consumidor · **Prioridad:** Alta · **Puntos:** 8

> Estado: especificación funcional de la historia. La implementación y sus pruebas
> se incorporan en los cambios posteriores a este documento.

### Historia de usuario

**Dado** un consumidor autenticado que desea comprar un producto digital,
**Para** que obtenga el producto de forma segura y sin cobros duplicados,
**Que** cree una orden, pague en la pasarela y reciba la confirmación.

**Beneficio esperado:** el comprador completa la compra con confianza y la
plataforma evita fraudes, duplicados y órdenes inconsistentes.

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-40 | Comercio | Órdenes | Crear orden | PRC-40 |
| FUN-41 | Comercio | Órdenes | Cancelar orden | PRC-41 |
| FUN-42 | Comercio | Pagos | Procesar pago (checkout) | PRC-42 |
| FUN-43 | Comercio | Pagos | Confirmar pago (webhook) | PRC-43 |

## Endpoints

Todas las respuestas usan el sobre `{ message, data, success }`.

| FUN | Método | Ruta | Resultado |
|---|---|---|---|
| FUN-40 | `POST` | `/api/v1/commerce/orders` | `201`, orden pendiente; `404`/`409` si no es comprable |
| FUN-42 | `POST` | `/api/v1/commerce/orders/{id}/checkout` | `200`, referencia y URL de pasarela; `400`/`404`/`409` |
| FUN-43 | `POST` | `/api/v1/commerce/payments/webhook` | `200`, confirmación; `400` si la firma, el monto o la referencia no son válidos |
| FUN-41 | `POST` | `/api/v1/commerce/orders/{id}/cancel` | `200`, orden cancelada y reserva liberada; `404`/`409` |

### Autorización y origen del comprador

- Se reutiliza el resolvedor de actor de la API: `Authorization: Bearer <token>`
  o, mientras se integra la autenticación, `X-Actor-Id` / `X-Actor-Roles`,
  igual que HU-03 a HU-11.
- Toda operación requiere consumidor autenticado (`401` si no hay actor).
- `compradorId` **siempre** se toma del actor autenticado; un `compradorId` o
  `userId` enviado en el cuerpo se ignora o se rechaza con `400`.
- Una orden ajena responde `404` (no `403`) para no revelar su existencia.

### POST `/api/v1/commerce/orders` (FUN-40)

Cuerpo: `{ "productId": "prod_100" }`.

Validaciones, en este orden:

1. El producto existe (`404 PRODUCT_NOT_FOUND`).
2. El producto está `publicado` y no `archivado` (`409 PRODUCT_NOT_AVAILABLE`;
   también se admite `404` para no exponer productos retirados).
3. El actor está autenticado como consumidor (`401 CONSUMER_REQUIRED`).
4. No existe licencia vigente del mismo producto para ese comprador
   (`409 ORDER_DUPLICATE`, código estable: `LICENSE_ALREADY_ACTIVE`).
5. No existe otra orden `pendiente` no vencida del mismo comprador y producto
   (`409 ORDER_PENDING`). La orden pendiente actúa como reserva temporal.

Cálculo (aritmética decimal, nunca `float`):

- `precio` = precio publicado del producto en COP.
- `comision` = `Decimal(precio) * Decimal(COM-01) / 100`, redondeada a la unidad
  de COP con `ROUND_HALF_UP` (COM-01 = 15 % según el ejemplo normativo).
- `netoProductor` = `precio - comision` (COM-02).
- `vencimiento` = `fechaCreacion + COM-05` minutos. COM-05 es un parámetro de
  Comercio; su valor se resuelve desde la configuración vigente, sin copiarlo
  en el código ni en los parámetros de Catálogo/Comunidad.
- `estado` inicial = `pendiente`.

```json
{
  "message": "Orden creada correctamente.",
  "data": {
    "id": "ord_500",
    "productId": "prod_100",
    "compradorId": "usr_001",
    "precio": 45000,
    "comision": 6750,
    "netoProductor": 38250,
    "estado": "pendiente",
    "fechaCreacion": "2026-10-25T18:00:00Z",
    "vencimiento": "2026-10-25T18:30:00Z"
  },
  "success": true
}
```

El precio y la moneda se congelan en la orden: cambios posteriores del producto
no alteran el importe a cobrar.

### POST `/api/v1/commerce/orders/{id}/checkout` (FUN-42)

Requiere la cabecera `Idempotency-Key` con una clave única del cliente. Solo se
puede hacer checkout de una orden `pendiente` no vencida y propiedad del actor.

1. Si la clave ya fue usada, se devuelve **la misma respuesta** y no se crea
   otra sesión de pago ni se realiza otro cobro.
2. Si no hay clave, responde `400 IDEMPOTENCY_KEY_REQUIRED`.
3. Se registra la referencia de pago devuelta por la pasarela y se guarda la
   relación `Idempotency-Key` → respuesta antes de responder al cliente.
4. La orden sigue `pendiente` hasta que llegue el webhook aprobado.

```json
{
  "message": "Checkout iniciado correctamente.",
  "data": {
    "ordenId": "ord_500",
    "estado": "pendiente",
    "referenciaPago": "pay_900",
    "checkoutUrl": "https://pasarela.test/checkout/pay_900",
    "vencimiento": "2026-10-25T18:30:00Z"
  },
  "success": true
}
```

### POST `/api/v1/commerce/payments/webhook` (FUN-43)

Convención de la pasarela: cuerpo JSON crudo, cabecera
`X-Commerce-Signature: sha256=<hex>` con HMAC-SHA256 del cuerpo exacto usando el
secreto configurado, y `eventId` único en el cuerpo. La validación ocurre antes
de cualquier escritura.

1. **Firma:** se calcula el HMAC sobre los bytes originales del cuerpo con
   comparación en tiempo constante. Firma ausente o inválida → `400
   WEBHOOK_INVALID_SIGNATURE`; la orden no cambia.
2. **Referencia:** `reference` / `referenciaPago` debe corresponder a una orden
   existente (`400 WEBHOOK_REFERENCE_INVALID`).
3. **Monto y moneda:** el importe confirmado debe ser exactamente `precio` de la
   orden y la moneda `COP` (`400 WEBHOOK_AMOUNT_MISMATCH`).
4. **Estado:** solo se confirman eventos aprobados; un evento rechazado mantiene
   la orden `pendiente` y termina en `200` sin emitir licencia.
5. **Idempotencia:** `eventId` se persiste. Un evento repetido responde `200` con
   la misma confirmación y **no** emite una segunda licencia ni un segundo cobro.
6. **Transición:** la orden pasa a `pagada`, se registra `fechaPago` y se emite
   la licencia **después del commit** del pago. Si la emisión falla, el pago se
   conserva y se reintenta sin cobrar de nuevo.

```json
{
  "message": "Pago confirmado correctamente.",
  "data": {
    "ordenId": "ord_500",
    "estado": "pagada",
    "licenciaId": "lic_001",
    "fechaPago": "2026-10-25T18:05:00Z"
  },
  "success": true
}
```

Tras el commit se publica el evento `order.paid` con `ordenId`, `productoId`,
`compradorId`, `precio`, `comision`, `netoProductor`, `licenciaId` y `fechaPago`.
El evento es el disparador de notificaciones y métricas; no se publica si la
validación falló.

### POST `/api/v1/commerce/orders/{id}/cancel` (FUN-41)

Solo aplica a órdenes `pendientes` (incluye órdenes vencidas). Una orden
`pagada` responde `409 ORDER_ALREADY_PAID` porque ya generó licencia. Una orden
ya cancelada responde `409 ORDER_NOT_CANCELLABLE`. Al cancelar se libera la
reserva: el comprador puede crear una nueva orden para el mismo producto.

```json
{
  "message": "Orden cancelada correctamente.",
  "data": {
    "id": "ord_500",
    "productId": "prod_100",
    "compradorId": "usr_001",
    "estado": "cancelada",
    "fechaCancelacion": "2026-10-25T18:10:00Z"
  },
  "success": true
}
```

Un checkout iniciado no bloquea la cancelación: si el webhook llega después de
la cancelación, se responde `200` sin cambiar la orden y sin emitir licencia.

## Errores

| Situación | HTTP | `data.codigo` |
|---|---|---|
| Sin actor autenticado | 401 | `CONSUMER_REQUIRED` |
| Orden ajena o inexistente | 404 | `ORDER_NOT_FOUND` |
| Producto inexistente | 404 | `PRODUCT_NOT_FOUND` |
| Producto no publicado / archivado | 409 | `PRODUCT_NOT_AVAILABLE` |
| Licencia vigente previa | 409 | `LICENSE_ALREADY_ACTIVE` |
| Orden pendiente vigente | 409 | `ORDER_PENDING` |
| Falta `Idempotency-Key` | 400 | `IDEMPOTENCY_KEY_REQUIRED` |
| Orden no pendiente para checkout | 409 | `ORDER_NOT_PENDING` |
| Orden vencida para checkout | 409 | `ORDER_EXPIRED` |
| Firma HMAC inválida | 400 | `WEBHOOK_INVALID_SIGNATURE` |
| Referencia desconocida | 400 | `WEBHOOK_REFERENCE_INVALID` |
| Monto o moneda divergente | 400 | `WEBHOOK_AMOUNT_MISMATCH` |
| Cancelar orden pagada/cancelada | 409 | `ORDER_NOT_CANCELLABLE` |

Ninguna respuesta de error modifica la orden, emite licencia ni publica
`order.paid`.

## Decisiones técnicas y límites con otros módulos

1. **Decimal:** comisión y neto se calculan con `Decimal` y se redondean a COP;
   se guardan como enteros en la orden para evitar derivas de `float`.
2. **Idempotencia:** las claves de checkout y los `eventId` del webhook se
   persisten con su respuesta. Un reintento nunca duplica sesión, cobro,
   licencia ni evento.
3. **Licencias:** la tabla `licencias` y el formato `lic_NNN` pertenecen a HU-15
   (HU-08 la crea y HU-10 añade `actor_id`). HU-14 **reutiliza** ese contrato
   (`attach_license` / `add_license`) y no redefine la tabla ni su esquema.
4. **Parámetros:** `COM-01`, `COM-02` y `COM-05` son de Comercio. La
   parametrización de Catálogo (HU-13) y de Comunidad (HU-21) rechaza
   explícitamente el prefijo `COM-`, por lo que no hay solapamiento de código ni
   de alcances (`admin.catalog.parameters.write`, `admin.community.parameters.write`).
5. **Consumidor aguas abajo:** HU-18 exige compra acreditada (COMU-04) y HU-10
   muestra detalle licenciado. La licencia emitida por FUN-43 satisface ambas
   reglas; no se crea un segundo registro de propiedad.
6. **Eventos:** `order.paid` se publica después del commit, con el mismo patrón
   de `AuditEvent` y bandeja de notificaciones usado por HU-11/HU-20.
7. **Vencimiento:** una orden `pendiente` vencida deja de ser reserva; el
   checkout responde `409 ORDER_EXPIRED` y se permite crear una nueva orden.

## Criterios de aceptación

- [ ] `POST /orders` valida producto publicado, comprador autenticado y ausencia de licencia previa.
- [ ] Una compra duplicada responde `409`.
- [ ] La orden calcula precio, comisión COM-01 y neto COM-02 con decimal.
- [ ] La orden pendiente vence en COM-05 minutos.
- [ ] `POST /checkout` exige y persiste `Idempotency-Key`.
- [ ] `POST /payments/webhook` valida firma HMAC, monto, referencia e idempotencia.
- [ ] Un webhook inválido responde `400` y no cambia la orden.
- [ ] `POST /cancel` solo aplica a órdenes no pagadas.
- [ ] La orden contiene `id`, `productId`, `compradorId`, `precio`, `comision`,
      `netoProductor`, `estado` y `fechaCreacion`.
- [ ] La confirmación contiene `ordenId`, `estado`, `licenciaId` y `fechaPago`.
- [ ] Los errores usan el sobre `{ message, data, success }`.

## Casos de prueba previstos

1. **Compra exitosa:** producto publicado y comprador sin licencia → orden,
   checkout y webhook aprobado → orden `pagada`, licencia emitida y evento
   `order.paid` publicado una sola vez.
2. **Compra duplicada:** licencia activa del mismo producto → `409` al crear
   otra orden; tampoco se crea orden pendiente.
3. **Webhook inválido:** orden pendiente + firma incorrecta → `400` y orden sin
   cambios (sin licencia ni evento).
4. **Cancelar orden pendiente:** orden pendiente → `200`, estado `cancelada` y
   reserva liberada (nueva orden permitida).
5. **Producto no disponible:** producto archivado → `409` o `404`, sin orden.
6. **Idempotencia:** mismo `Idempotency-Key` y mismo `eventId` repetidos → una
   sola sesión, una sola licencia, una sola confirmación.

## Definición de hecho

- [ ] Órdenes y pagos documentados.
- [ ] Cálculo de comisión probado con decimal.
- [ ] Idempotencia y firma verificadas.
- [ ] Licencia y evento `order.paid` comprobados.
- [ ] Cancelación de orden probada.
