# [HU-10] Búsqueda, filtros, vitrina y detalle — implementación

**Módulo:** Catálogo · **Submódulos:** SUB-11, SUB-12 · **Funciones:** FUN-28 a FUN-31
**Actor:** Visitante, Consumidor · **Prioridad:** Alta · **Puntos:** 5

### Historia de usuario

**Dado** un visitante o consumidor que busca un producto digital,
**Para** que encuentre rápidamente una opción que cumpla sus intereses y edad,
**Que** busque por texto, filtre por categoría, edad y precio, y consulte vitrina y detalle.

| FUN | Proceso | Funcionalidad |
|---|---|---|
| FUN-28 | PRC-28 | Buscar productos |
| FUN-29 | PRC-29 | Filtrar productos |
| FUN-30 | PRC-30 | Consultar vitrina |
| FUN-31 | PRC-31 | Consultar detalle del producto |

## Endpoints

Todas las respuestas usan el sobre `{ message, data, success }`.

| FUN | Método | Ruta | Resultado |
|---|---|---|---|
| FUN-28/29 | `GET` | `/api/v1/catalog/products` | `200`, búsqueda paginada y filtrada |
| FUN-30 | `GET` | `/api/v1/catalog/showcase` | `200`, vitrina agrupada por categoría |
| FUN-31 | `GET` | `/api/v1/catalog/products/{id}` | `200` publicado/licenciado; `404` otherwise |

### GET `/products` (FUN-28 / FUN-29)

Solo devuelve productos con `estado = 'publicado' AND activo = 1`.

| Parámetro | Tipo | Regla |
|---|---|---|
| `q` | `str` | Texto normalizado (sin acentos), con sinónimos y tolerancia a errores |
| `categoria` | `str` | Debe existir y estar activa (CAT-13) |
| `edad` | `int` | CAT-03: `0 ≤ edad ≤ 99`; compatible si `edadMinima ≤ edad ≤ edadMaxima` |
| `precioMin` / `precioMax` | `int` | CAT-01: enteros ≥ 3500 COP y `precioMin ≤ precioMax` |
| `orden` | `str` | `relevancia`, `fecha_desc`, `fecha_asc`, `precio_asc`, `precio_desc` (alias: `fecha`, `precio`, `recientes`, …) |
| `pagina` | `int` | ≥ 1, base 1 |
| `tamanioPagina` | `int` | `1..CATALOG_MAX_PAGE_SIZE` (100 por defecto, 20 por omisión) |

Los filtros se combinan con **AND**. El orden es estable: se desempata por
`id` y, en relevancia, por fecha descendente.

Ejemplo — `GET /api/v1/catalog/products?q=ilustracion&edad=12`:

```json
{
  "message": "Búsqueda realizada correctamente.",
  "data": {
    "items": [
      {
        "id": "prod_001",
        "nombre": "Pack de ilustraciones",
        "precio": 45000,
        "moneda": "COP",
        "autor": "Ana Torres",
        "categoria": "Ilustración",
        "categoriaId": "cat_001",
        "calificacion": 4.8,
        "miniatura": "https://cdn.digiverso.com/a.webp",
        "edadMinima": 0,
        "edadMaxima": 99
      }
    ],
    "total": 1,
    "pagina": 1,
    "tamanioPagina": 20
  },
  "success": true
}
```

Cada item expone únicamente datos públicos: no incluye `autorId`, correos ni
totales de licencias. `calificacion` es un número entre 0 y 5 (`0` cuando aún
no hay reseñas registradas).

### GET `/showcase` (FUN-30)

```json
{
  "message": "Vitrina consultada correctamente.",
  "data": {
    "categorias": [
      {
        "id": "cat_001",
        "nombre": "Ilustración",
        "total": 2,
        "productos": [ /* ProductSearchItem */ ]
      }
    ],
    "total": 2
  },
  "success": true
}
```

La respuesta se construye desde una caché en memoria **por categoría**
(`InMemoryShowcaseCache`). Cualquier creación, edición o transición del
producto invalida la cach completa, por lo que archivar un producto lo retira
inmediatamente de la vitrina.

### GET `/products/{id}` (FUN-31)

Reglas de visibilidad:

| Situación | Resultado |
|---|---|
| Publicado | `200` para visitantes y consumidores |
| No publicado + autor del producto | `200` (con `autorId` y `licenciasActivas`) |
| No publicado + administrador | `200` (con datos de gestión) |
| No publicado + licencia vigente del actor | `200`, con la licencia en `data.licencia` |
| No publicado + visitante sin licencia | `404` |

El detalle incluye descripción, `edadMinima`/`edadMaxima`, `medios`,
`calificacion`, `miniatura`, `autor` (nombre público) y `licencia` cuando el
actor tiene una licencia vigente. Para visitantes/consumidores se omite
`autorId` (queda `null`) y `licenciasActivas` (queda `0`).

```json
{
  "message": "Producto consultado correctamente.",
  "data": {
    "id": "prod_001",
    "nombre": "Pack de ilustraciones",
    "descripcion": "Ilustraciones digitales en alta resolución.",
    "calificacion": 4.8,
    "miniatura": "https://cdn.digiverso.com/a.webp",
    "autor": "Ana Torres",
    "categoria": "Ilustración",
    "edadMinima": 0,
    "edadMaxima": 99,
    "medios": [{ "id": null, "tipo": "imagen", "url": "https://cdn.digiverso.com/a.webp", "orden": 0 }],
    "autorId": null,
    "licencia": null
  },
  "success": true
}
```

## Reglas y errores

| Regla | Código | Resultado |
|---|---|---|
| Edad fuera de CAT-03 | `CATALOG_QUERY_INVALID` | `422` |
| Precio inferior a CAT-01 o rango invertido | `CATALOG_QUERY_INVALID` | `422` |
| Categoría inexistente/inactiva | `CATALOG_QUERY_INVALID` | `422` |
| Orden no permitido | `CATALOG_QUERY_INVALID` | `422` |
| Paginación fuera de rango | `CATALOG_QUERY_INVALID` | `422` |
| Producto no visible | `PRODUCT_NOT_FOUND` | `404` |

## Decisiones técnicas

- **Índice:** tabla FTS5 `productos_busqueda` (con `unicode61 remove_diacritics 2`)
  que guarda texto normalizado del nombre, descripción, autor, categorías y sus
  sinónimos. Si SQLite no incluye FTS5 se crea una tabla relacional equivalente.
  El índice se reconstruye automáticamente al iniciar si está desincronizado y
  se actualiza en cada `save`/`update`.
- **Sinónimos y tolerancia:** `app/domain/catalog_search.py` expansiona
  términos (`ilustración → dibujo/arte/imagen`, `curso → tutorial/clase`, …) y
  aplica distancia de Levenshtein (1 error, 2 en palabras largas) como respaldo
  cuando el MATCH de FTS5 no encuentra coincidencias. El puntaje prioriza
  coincidencias exactas en el nombre.
- **Capas:** las reglas de consulta son puras y viven en el dominio; el
  repositorio solo filtra/ordena/pagina y el servicio valida categorías activas
  y resuelve la visibilidad del detalle.
- **Privacidad:** `autorId` y `licenciasActivas` se rellenan solo para el autor
  o un administrador; las respuestas públicas usan `autor` (nombre legible).
- **Licencias:** se añadió `licencias.actor_id` (migración idempotente) para
  resolver la licencia del actor autenticado sin exponer los datos del productor.

### Parámetros configurables

| Variable | Valor por defecto | Uso |
|---|---|---|
| `CATALOG_DEFAULT_PAGE_SIZE` | `20` | Tamaño de página por omisión |
| `CATALOG_MAX_PAGE_SIZE` | `100` | Límite máximo de paginación |

## Pruebas

```bash
pytest -q
```

`tests/test_catalog_discovery_api.py` cubre los cinco casos de aceptación:
búsqueda por texto (solo publicados), filtros (edad, categoría, precio, orden),
producto no publicado (visitante `404`, autor/admin/licenciado `200`), vitrina
agrupada con caché e invalidación, y paginación estable.
`tests/test_catalog_search_domain.py` cubre las reglas puras de normalización,
sinónimos, tolerancia y validación. La suite completa pasa con 94 pruebas.
