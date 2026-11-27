# [HU-19] Seguimiento, feed, intereses y recomendaciones — implementación

**Módulo:** Comunidad · **Submódulos:** SUB-24, SUB-25, SUB-26
**Funciones:** FUN-58, FUN-59, FUN-60, FUN-61, FUN-62
**Actor:** Consumidor · **Prioridad:** Media · **Puntos:** 8

### Historia de usuario

**Dado** un consumidor que quiere descubrir productores y productos afines,
**Para** que reciba novedades y recomendaciones relevantes sin buscar manualmente,
**Que** siga y deje de seguir productores, consulte su feed, configure intereses y reciba recomendaciones.

### Beneficio esperado

El comprador descubre contenido de su interés y los productores amplían su audiencia.

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-58 | Comunidad | Seguimiento | Seguir usuario | PRC-58 |
| FUN-59 | Comunidad | Seguimiento | Dejar de seguir usuario | PRC-59 |
| FUN-60 | Comunidad | Feed | Consultar feed de seguidos | PRC-60 |
| FUN-61 | Comunidad | Intereses y recomendaciones | Configurar intereses | PRC-61 |
| FUN-62 | Comunidad | Intereses y recomendaciones | Consultar recomendaciones | PRC-62 |

## Flujo esperado

1. El consumidor sigue a un productor.
2. El sistema valida que no sea auto-seguimiento y respeta COMU-05.
3. El consumidor consulta el feed de los productores seguidos.
4. Configura sus categorías de interés hasta COMU-08.
5. El sistema recomienda productos excluyendo comprados y propios.

## Endpoints

Todas las respuestas usan el sobre `{ message, data, success }`. El actor se
resuelve con `Authorization: Bearer <token>` o con `X-Actor-Id` / `X-Actor-Roles`,
igual que el resto de la API; el usuario seguido siempre se toma de la ruta.

| FUN | Método | Ruta | Resultado |
|---|---|---|---|
| FUN-58 | `POST` | `/api/v1/community/users/{id}/follow` | `201`, relación creada |
| FUN-59 | `DELETE` | `/api/v1/community/users/{id}/follow` | `200`, relación eliminada |
| FUN-60 | `GET` | `/api/v1/community/feed/following` | `200`, feed paginado |
| FUN-61 | `PUT` | `/api/v1/community/me/interests` | `200`, intereses actualizados |
| FUN-62 | `GET` | `/api/v1/community/feed/recommended` | `200`, recomendaciones |

### POST `/users/{id}/follow` (FUN-58)

Validaciones, en este orden:

1. **Auto-seguimiento**: se rechaza en dominio con `400 FOLLOW_SELF`, antes de
   consultar la cuenta; es una regla de negocio, no una comprobación de existencia.
2. **Duplicado**: si la relación ya existe, `409 FOLLOW_DUPLICATE`.
3. **COMU-05**: si se alcanzó el máximo de seguidos, `409 FOLLOW_LIMIT`.
4. El usuario indicado debe existir; en caso contrario, `404 USER_NOT_FOUND`.

```json
{
  "message": "Usuario seguido correctamente.",
  "data": {
    "seguidorId": "usr_comprador",
    "seguidoId": "usr_001",
    "fecha": "2026-11-26T18:00:00Z",
    "totalSiguiendo": 1,
    "totalSeguidores": 1
  },
  "success": true
}
```

### DELETE `/users/{id}/follow` (FUN-59)

Elimina la relación (operación idempotente: `eliminado` indica si existía) y
recalcula los contadores `siguiendo` del actor y `seguidores` del seguido. Un
usuario inexistente responde `404 USER_NOT_FOUND`.

```json
{
  "message": "Se dejó de seguir al usuario correctamente.",
  "data": {
    "seguidorId": "usr_comprador",
    "seguidoId": "usr_001",
    "eliminado": true,
    "totalSiguiendo": 0,
    "totalSeguidores": 0
  },
  "success": true
}
```

### GET `/feed/following` (FUN-60)

Solo productos con `estado = 'publicado' AND activo = 1` cuyo `autor_id` esté
entre los usuarios seguidos.

| Parámetro | Tipo | Regla |
|---|---|---|
| `pagina` | `int` | ≥ 1, base 1 |
| `tamanioPagina` | `int` | `1..COMU_07_MAX_PAGE_SIZE`; 20 por omisión |

```json
{
  "message": "Feed consultado correctamente.",
  "data": {
    "items": [
      { "productId": "prod_100", "nombre": "Pack de ilustraciones", "autor": "Ana Torres", "precio": 45000, "moneda": "COP", "fecha": "2026-11-26T18:00:00Z", "categoria": "cat_001", "miniatura": "https://cdn.digiverso.com/a.webp" }
    ],
    "total": 1,
    "pagina": 1,
    "tamanioPagina": 20
  },
  "success": true
}
```

Cada item contiene producto (`productId`, `nombre`), autor, precio, moneda,
fecha de publicación, categoría y miniatura. El orden es fecha descendente con
`id` como desempate estable.

### PUT `/me/interests` (FUN-61)

Cuerpo: `{ "categorias": ["cat_001", "cat_002"] }`. Se eliminan duplicados, se
exige que cada categoría exista y esté activa y se aplica COMU-08. La lista se
sustituye por completo; enviar `[]` limpia los intereses.

```json
{
  "message": "Intereses actualizados correctamente.",
  "data": { "categorias": ["cat_001", "cat_002"], "total": 2, "maximo": 10 },
  "success": true
}
```

### GET `/feed/recommended` (FUN-62)

Excluye productos propios (`autor_id = actor`) y comprados (licencia vigente del
actor). La puntuación combina coincidencia con intereses (3 puntos por categoría,
máximo 3), señal de compra (licencias vigentes, hasta 1 punto) y novedad
(0,5 puntos si tiene menos de `COMU_10_RECENT_DAYS` días). El `motivo` explica
la recomendación con el nombre legible de la categoría.

COMU-09 limita la cantidad devuelta y COMU-10 fija el orden
`puntuacion_desc, fecha_desc, id_asc`.

```json
{
  "message": "Recomendaciones consultadas correctamente.",
  "data": {
    "items": [
      { "productId": "prod_100", "nombre": "Pack de ilustraciones", "autor": "Ana Torres", "precio": 45000, "moneda": "COP", "categoria": "Ilustración", "fecha": "2026-11-26T18:00:00Z", "motivo": "Coincide con tus intereses: Ilustración.", "puntuacion": 3.5 }
    ],
    "total": 1,
    "limite": 20,
    "orden": "puntuacion_desc,fecha_desc,id_asc"
  },
  "success": true
}
```

## Estructura de la información

- El feed contiene `items`, `total` y `pagina` (además de `tamanioPagina`).
- Cada item del feed contiene producto, autor, precio y fecha.
- Las recomendaciones contienen producto, `motivo` y `puntuacion`.

## Reglas y errores

| Situación | Código HTTP | `data.codigo` | `data.regla` |
|---|---|---|---|
| Auto-seguimiento | `400` | `FOLLOW_SELF` | `SELF_FOLLOW` |
| Seguimiento duplicado | `409` | `FOLLOW_DUPLICATE` | `FOLLOW_DUPLICATE` |
| Límite COMU-05 | `409` | `FOLLOW_LIMIT` | `COMU-05` |
| Usuario inexistente | `404` | `USER_NOT_FOUND` | `USER_NOT_FOUND` |
| Paginación COMU-07 | `422` | `COMMUNITY_QUERY_INVALID` | `COMU-07` |
| Categoría inexistente/inactiva | `400` | `INTEREST_INVALID` | `INTEREST_INVALID` |
| Límite COMU-08 | `409` | `INTEREST_LIMIT` | `COMU-08` |

## Decisiones técnicas

- **Dominio puro**: `app/domain/community.py` valida seguimiento, paginación e
  intereses y calcula la puntuación/orden de recomendaciones. Las reglas no
  dependen de HTTP ni de SQLite.
- **Fan-out híbrido y caché**: `app/cache/community_feed.py` materializa el feed
  y las recomendaciones por usuario. Seguir, dejar de seguir y cambiar intereses
  invalidan las entradas del usuario. La firma de la caché incluye los seguidos,
  los intereses, los productos comprados y el estado de los publicados, por lo
  que una publicación nueva se refleja sin acoplar HU-19 a HU-08.
- **Contadores eventuales**: `community_stats` deriva `seguidores` y `siguiendo`
  de la tabla `community_follows`; cada escritura recalcula ambos lados y el
  repositorio expone `recompute_stats` para reconciliarlos si se necesita.
- **Sin módulo de Comercio**: `PurchaseGateway` define el contrato de compra y
  `LicensePurchaseGateway` lo resuelve con las licencias vigentes de Catálogo.
  Al conectar Comercio solo se sustituye el adaptador.
- **Tablas propias**: `community_follows`, `community_interests` y
  `community_stats` se crean en `app/repository/community.py`, sin modificar el
  esquema compartido, para evitar colisiones con HU-11/HU-12/HU-13/HU-18.
- **Parámetros propios**: `CommunitySettings` vive en el dominio y se lee de
  `.env`, de modo que no se modifica `app/core/config.py` (HU-18 ya añade allí
  parámetros COMU-01..04).

### Parámetros configurables

| Variable | Valor por defecto | Uso |
|---|---|---|
| `COMU_05_MAX_FOLLOWING` | `200` | Máximo de usuarios seguidos (COMU-05) |
| `COMU_07_DEFAULT_PAGE_SIZE` / `COMU_07_MAX_PAGE_SIZE` | `20` / `100` | Paginación del feed (COMU-07) |
| `COMU_08_MAX_INTERESTS` | `10` | Máximo de categorías de interés (COMU-08) |
| `COMU_09_MAX_RECOMMENDATIONS` | `20` | Máximo de recomendaciones (COMU-09) |
| `COMU_10_RECENT_DAYS` | `30` | Ventana de novedad en la puntuación (COMU-10) |

Los valores numéricos de COMU-05/07/08/09/10 no estaban definidos en la
especificación; se fijan aquí y son sobreescribibles por entorno.

## Pruebas

```bash
pytest -q
```

`tests/test_community_feed_domain.py` cubre auto-seguimiento, duplicados,
COMU-05, COMU-07, COMU-08, puntuación y orden COMU-10.
`tests/test_community_feed_api.py` cubre los cinco casos de aceptación (seguir,
auto-seguimiento, feed de seguidos, intereses excedidos y recomendaciones), más
404 de usuario inexistente, paginación inválida, invalidación de caché al
publicar/dejar de seguir, exclusión de comprados y propios, y límite COMU-09.

## Definición de hecho

- [x] Seguimiento, feed, intereses y recomendaciones documentados.
- [x] Límites y auto-seguimiento probados.
- [x] Exclusión de comprados y propios verificada.
- [x] Cache de feed invalidada.
- [x] Contadores actualizados.
