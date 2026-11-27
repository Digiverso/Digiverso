# [HU-18] Reseñas y calificaciones — implementación

**Módulo:** Comunidad · **Submódulos:** SUB-22, SUB-23 · **Funciones:** FUN-54 a FUN-57
**Actor:** Consumidor · **Prioridad:** Media · **Puntos:** 5

### Historia de usuario

**Dado** un consumidor que compró un producto digital,
**Para** que comparta su experiencia y ayude a otros compradores a decidir,
**Que** publique una reseña con calificación, consulte reseñas y vea la calificación promedio.

| FUN | Proceso | Funcionalidad |
|---|---|---|
| FUN-54 | PRC-54 | Publicar reseña |
| FUN-55 | PRC-55 | Consultar reseñas |
| FUN-56 | PRC-56 | Calcular calificación promedio |
| FUN-57 | PRC-57 | Consultar calificación |

## Endpoints

Todas las respuestas usan el sobre `{ message, data, success }`. El actor se
resuelve con `Authorization: Bearer <token>` o con `X-Actor-Id` / `X-Actor-Roles`,
igual que el resto de la API; `userId` nunca se toma del cuerpo.

| FUN | Método | Ruta | Resultado |
|---|---|---|---|
| FUN-54 | `POST` | `/api/v1/community/products/{id}/reviews` | `201`, reseña publicada |
| FUN-55 | `GET` | `/api/v1/community/products/{id}/reviews` | `200`, reseñas visibles paginadas |
| FUN-56/57 | `GET` | `/api/v1/community/products/{id}/rating` | `200`, promedio y total |

### POST `/reviews` (FUN-54)

Cuerpo: `{ "calificacion": 5, "texto": "Excelente calidad y entrega inmediata." }`.

Validaciones, en este orden:

1. El producto existe (`404 PRODUCT_NOT_FOUND`).
2. **COMU-04**: si está activo, el actor acredita compra o licencia vigente;
   si no, `403 REVIEW_PURCHASE_REQUIRED`.
3. **COMU-03**: si está activo, solo una reseña por usuario y producto;
   si ya existe, `409 REVIEW_DUPLICATE`.
4. **COMU-01**: calificación entera entre 1 y 5; si no, `400 REVIEW_RATING_INVALID`.
5. **COMU-02**: texto saneado de 10 a 1000 caracteres; si no, `400 REVIEW_TEXT_INVALID`.

```json
{
  "message": "Reseña publicada correctamente.",
  "data": {
    "id": "rev_300",
    "productId": "prod_100",
    "userId": "usr_001",
    "calificacion": 5,
    "texto": "Excelente calidad y entrega inmediata.",
    "fecha": "2026-10-25T18:00:00Z"
  },
  "success": true
}
```

### GET `/reviews` (FUN-55)

| Parámetro | Tipo | Regla |
|---|---|---|
| `pagina` | `int` | ≥ 1, base 1 |
| `tamanioPagina` | `int` | `1..COMMUNITY_MAX_PAGE_SIZE` (100); 20 por omisión |

Orden estable: fecha descendente y, como desempate, `id` descendente. Solo se
devuelven reseñas con `visible = 1`. El texto devuelto ya está saneado.

```json
{
  "message": "Reseñas consultadas correctamente.",
  "data": {
    "items": [ /* ReviewItem */ ],
    "total": 12,
    "pagina": 1,
    "tamanioPagina": 20
  },
  "success": true
}
```

### GET `/rating` (FUN-56 / FUN-57)

```json
{
  "message": "Calificación consultada correctamente.",
  "data": {
    "promedio": 4.0,
    "total": 2,
    "distribucion": { "1": 0, "2": 0, "3": 1, "4": 0, "5": 1 }
  },
  "success": true
}
```

`promedio` se redondea a dos decimales; sin reseñas es `0.0` y la distribución
queda en cero para los cinco valores.

## Errores

| Situación | Código HTTP | `data.codigo` | `data.regla` |
|---|---|---|---|
| Sin compra ni licencia | `403` | `REVIEW_PURCHASE_REQUIRED` | `COMU-04` |
| Reseña duplicada | `409` | `REVIEW_DUPLICATE` | `COMU-03` |
| Calificación 0, 6 o no entera | `400` | `REVIEW_RATING_INVALID` | `COMU-01` |
| Texto vacío, corto o largo | `400` | `REVIEW_TEXT_INVALID` | `COMU-02` |
| Producto inexistente | `404` | `PRODUCT_NOT_FOUND` | — |
| Paginación fuera de rango | `422` | `CATALOG_QUERY_INVALID` | — |

## Decisiones técnicas

- **Sin módulo de Comercio**: `app/services/commerce.py` define el contrato
  `PurchaseGateway` y una implementación local que consulta las licencias
  vigentes de Catálogo. Al integrar Comercio solo se sustituye el adaptador;
  el servicio de reseñas no cambia.
- **Dominio puro**: `app/domain/reviews.py` sanea texto (elimina `script`,
  `style`, etiquetas y caracteres de control), valida COMU-01/02 y calcula el
  promedio a partir de una agregación.
- **Persistencia**: tabla `reviews` con índices por producto/visibilidad y por
  usuario/producto. `visible = 0` conserva el histórico para Control de
  publicaciones; `ReviewService.hide_review` recalcula promedio y caché.
- **Caché y coherencia**: `InMemoryRatingCache` guarda la agregación por
  producto. Publicar u ocultar una reseña invalida y recalcula la caché,
  actualiza `productos.calificacion` e invalida la vitrina (HU-10), de modo
  que el detalle y la búsqueda muestran el promedio vigente.
- **Evento**: tras persistir, el servicio publica `review.created` en
  `InMemoryEventBus` (`app/repository/events.py`) con `id`, `productId`,
  `userId`, `calificacion`, `texto`, `fecha`, `promedio` y `total`. HU-20 puede
  consumirlo para notificar al productor.
- **Sanitización**: el texto se guarda ya limpio; ninguna capa necesita volver
  a interpretar HTML antes de mostrarlo.

### Parámetros configurables

| Variable | Valor por defecto | Uso |
|---|---|---|
| `COMU_01_MIN_RATING` / `COMU_01_MAX_RATING` | `1` / `5` | Rango de COMU-01 |
| `COMU_02_MIN_LENGTH` / `COMU_02_MAX_LENGTH` | `10` / `1000` | Longitud de COMU-02 |
| `COMU_03_UNIQUE_REVIEW` | `true` | Activa/desactiva la unicidad |
| `COMU_04_REQUIRE_PURCHASE` | `true` | Activa/desactiva la verificación de compra |
| `COMMUNITY_DEFAULT_PAGE_SIZE` / `COMMUNITY_MAX_PAGE_SIZE` | `20` / `100` | Paginación |

## Pruebas

```bash
pytest -q
```

`tests/test_community_reviews_domain.py` cubre normalización del texto, rango
de calificación, longitudes y agregación. `tests/test_community_reviews_api.py`
cubre los cinco casos de aceptación (reseña válida con promedio actualizado,
sin compra, duplicada, calificación 6 y consulta de promedio), además de
paginación, sanitización, evento `review.created`, retiro lógico y las
banderas COMU-03/COMU-04 desactivadas. La suite completa pasa con 193 pruebas.

## Definición de hecho

- [x] Reseñas y calificaciones documentadas.
- [x] Validación de compra y duplicados probada.
- [x] Promedio y distribución verificados.
- [x] Sanitización de texto activa.
- [x] Evento `review.created` publicado.
