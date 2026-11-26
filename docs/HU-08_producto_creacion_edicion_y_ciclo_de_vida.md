# [HU-08] Producto: creación, edición y ciclo de vida — implementación

**Módulo:** Catálogo · **Submódulo:** SUB-09 · **Funciones:** FUN-21 a FUN-25
**Actor:** Productor · **Prioridad:** Alta · **Puntos:** 8

### Historia de usuario

**Dado** un productor autenticado que desea vender una producción digital propia,
**Para** que publique su producto con reglas claras y controle su disponibilidad,
**Que** cree, edite, envíe a revisión, archive y reactive sus productos.

**Beneficio esperado:** el productor publica con autonomía y la plataforma
conserva reglas de autoría, precio, edad y estado.

| FUN | Proceso | Funcionalidad |
|---|---|---|
| FUN-21 | PRC-21 | Crear producto |
| FUN-22 | PRC-22 | Editar producto |
| FUN-23 | PRC-23 | Enviar producto a revisión |
| FUN-24 | PRC-24 | Archivar producto |
| FUN-25 | PRC-25 | Reactivar producto |

## Endpoints

Base: `/api/v1/catalog/products`. Todas las respuestas —correctas e incorrectas—
usan el sobre `message` / `data` / `success`.

| FUN | Método | Ruta | Resultado |
|---|---|---|---|
| FUN-21 | `POST` | `/products` | `201`, producto en `borrador` |
| FUN-22 | `PATCH` | `/products/{id}` | `200`, campos actualizados |
| FUN-23 | `POST` | `/products/{id}/submit-review` | `200`, estado `en_revision` |
| FUN-24 | `PATCH` | `/products/{id}/archive` | `200`, estado `archivado` |
| FUN-25 | `PATCH` | `/products/{id}/reactivate` | `200`, `publicado` u `en_revision` |
| — | `GET` | `/products` | Búsqueda paginada (solo publicados y activos; HU-10) |
| — | `GET` | `/products/{id}` | Detalle del producto (visibilidad en HU-10) |

### POST `/products` (FUN-21)

```json
{
  "nombre": "Pack de ilustraciones",
  "descripcion": "Pack de ilustraciones digitales en alta resolución.",
  "precio": 45000,
  "moneda": "COP",
  "edadMinima": 0,
  "edadMaxima": 99,
  "categorias": ["cat_001"],
  "medios": [{ "tipo": "imagen", "url": "https://cdn.digiverso.com/a.webp" }]
}
```

Respuesta `201`:

```json
{
  "message": "Producto creado en borrador.",
  "data": {
    "id": "prod_001",
    "nombre": "Pack de ilustraciones",
    "descripcion": "Pack de ilustraciones digitales en alta resolución.",
    "precio": 45000,
    "moneda": "COP",
    "edadMinima": 0,
    "edadMaxima": 99,
    "categorias": ["cat_001"],
    "estado": "borrador",
    "autorId": "usr_010",
    "medios": [{ "id": null, "tipo": "imagen", "url": "https://cdn.digiverso.com/a.webp", "orden": 0 }],
    "creadoEn": "2026-11-21T12:00:00+00:00",
    "actualizadoEn": "2026-11-21T12:00:00+00:00",
    "licenciasActivas": 0
  },
  "success": true
}
```

El campo `autorId` del cuerpo se acepta pero **se ignora**: el autor siempre se
toma del actor autenticado (`sub` del token `Authorization: Bearer …`, o de las
cabeceras `X-Actor-Id` / `X-Actor-Roles` mientras HU-01/04 no emitan tokens).

### PATCH `/products/{id}` (FUN-22)

Actualiza únicamente los campos enviados. Solo el autor puede editar. Un producto
de otro autor devuelve `403`; cambiar `autorId` no tiene efecto.

### POST `/products/{id}/submit-review` (FUN-23)

Exige al menos CAT-09 imágenes. Los medios pueden enviarse como objetos
`{ id, tipo, url, orden }` o como URLs sueltas (se cuentan como imágenes). Si no
hay suficientes imágenes devuelve `422` y el producto permanece en `borrador`.

### PATCH `/products/{id}/archive` (FUN-24)

Pasa a `archivado`, guarda un hash del contenido y retira el producto de la
vitrina (`activo = 0`). No toca las licencias ni los datos históricos.

### PATCH `/products/{id}/reactivate` (FUN-25)

Solo desde `archivado`:

- con cambios (contenido distinto al momento de archivar) → `en_revision`;
- sin cambios → `publicado` (y `activo = 1`, vuelve a la vitrina).

Las respuestas de transición añaden `estadoAnterior`, `transicion` y `fecha`
(fecha efectiva del cambio, ISO 8601 UTC).

## Ciclo de vida

```text
             create (FUN-21)
                   │
                   ▼
  ┌──────────── borrador ────────────┐
  │   editar · submit-review ·       │
  │   archive                        │
  └───────────────┬───────────────────┘
                  ▼
            en_revision  ──── editar: 409
                  │  archive
                  ▼
             archivado ◄────────── archive (desde cualquier estado activo)
                  │  editar (prepara cambios)
                  │  reactivate
          ┌───────┴────────┐
   con cambios        sin cambios
      ▼                   ▼
  en_revision          publicado ── editar · submit-review · archive
      ▲                   │
      └── (revisión) ─────┘
  rechazado ── editar · submit-review · archive
```

| Estado | Editar | Enviar a revisión | Archivar | Reactivar |
|---|:---:|:---:|:---:|:---:|
| `borrador` | sí | sí | sí | 409 |
| `en_revision` | 409 | 409 | sí | 409 |
| `publicado` | sí | sí | sí | 409 |
| `rechazado` | sí | sí | sí | 409 |
| `archivado` | sí | 409 | 409 | sí |

`reactivate` es la única forma de publicar desde esta HU: la aprobación de la
revisión pertenece a HU-11. Editar un producto archivado no lo publica; guarda
los cambios para que `reactivate` decida si debe volver a revisión.

## Reglas de negocio

| Regla | Código | Resultado |
|---|---|---|
| Precio mínimo CAT-01 (3.500 COP) y moneda COP | `PRODUCT_INVALID` | `422` |
| Rango de edad CAT-03 (`0 ≤ mín ≤ máx ≤ 99`) | `PRODUCT_INVALID` | `422` |
| Al menos CAT-09 imágenes para revisión | `PRODUCT_MEDIA_REQUIRED` | `422` |
| Longitud del nombre CAT-11 (2–120) | `PRODUCT_INVALID` | `422` |
| Longitud de la descripción CAT-12 (1–2000) | `PRODUCT_INVALID` | `422` |
| Entre 1 y 5 categorías CAT-13, únicas, existentes y activas | `PRODUCT_INVALID` | `422` |
| Producto inexistente | `PRODUCT_NOT_FOUND` | `404` |
| Editar/transicionar un producto ajeno | `CATALOG_FORBIDDEN` | `403` |
| Transición no permitida | `PRODUCT_INVALID_STATE` | `409` |
| Token de actor inválido | `CATALOG_FORBIDDEN` | `403` |

Todas estas reglas viven en `app/domain/product.py`; el servicio solo orquesta,
persiste y audita. La autoría se comprueba en el servicio antes de cualquier
escritura.

## Decisiones técnicas

- **Autor:** `autor_id` se fija con el actor resuelto por `get_actor`. Se añadió
  `ActorTokenManager` (HMAC-SHA256 sobre `SECRET_KEY`) para aceptar tokens
  firmados `Authorization: Bearer <token>`; las cabeceras `X-Actor-*` siguen
  vigentes como puente con las HU de autenticación.
- **Persistencia:** se amplió la tabla `productos` creada por HU-07 con una
  migración idempotente (`PRAGMA table_info` + `ALTER TABLE`), conservando
  `categoria_id`, `estado` y `activo` para no romper la regla FUN-19. La lista
  completa de categorías y los medios se guardan como JSON.
- **Vitrina:** `estado = 'publicado' AND activo = 1`. Archivar y enviar a
  revisión ponen `activo = 0`.
- **Licencias:** tabla `licencias` mínima para comprobar que FUN-24 no las
  modifica (`vigente` permanece en 1). La gestión completa corresponde a HU-15.
- **Auditoría:** se reutiliza `audit_log` con `entidad = 'producto'`. Cada
  escritura registra actor, roles, fecha y antes/después o transición.
- **Cambios al reactivar:** al archivar se guarda `archivo_hash` (SHA-256 del
  contenido). Si al reactivar el hash difiere —o el producto se editó mientras
  estaba archivado— se envía a revisión; en caso contrario se publica.

### Parámetros configurables

| Variable | Valor por defecto | Uso |
|---|---|---|
| `CAT_01_MIN_PRICE` | `3500` | Precio mínimo en COP |
| `CAT_03_MAX_AGE` | `99` | Edad máxima CAT-03 |
| `CAT_09_MIN_IMAGES` | `1` | Imágenes mínimas para revisión |
| `CAT_11_MIN_LENGTH` / `CAT_11_MAX_LENGTH` | `2` / `120` | Longitud del nombre |
| `CAT_12_MIN_LENGTH` / `CAT_12_MAX_LENGTH` | `1` / `2000` | Longitud de la descripción |
| `CAT_13_MAX_CATEGORIES` | `5` | Máximo de categorías por producto |
| `ACTOR_TOKEN_TTL_SECONDS` | `3600` | Vigencia del token de actor firmado |

Los valores numéricos de CAT-03/09/11/12/13 no estaban definidos en el
repositorio; se fijan en `Settings` y pueden sobreescribirse desde `.env` (HU-13
podrá gobernarlos después).

## Pruebas

```bash
pytest -q
```

`tests/test_product_domain.py` cubre las reglas puras; `tests/test_products_api.py`
cubre los seis casos de la historia más autoría por token, vitrina, auditoría y
transiciones inválidas. La suite completa pasa con 61 pruebas.
