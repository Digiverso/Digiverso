# Digiverso API

API del marketplace Digiverso. Incluye los módulos **Catálogo · Categorías**
(HU-07, FUN-17 a FUN-20), **Catálogo · Productos** (HU-08, FUN-21 a FUN-25) y
**Catálogo · Medios del producto** (HU-09, FUN-26 y FUN-27).

## Instalación y ejecución

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Documentación interactiva (OpenAPI): <http://localhost:8000/docs>

## Pruebas

```bash
pytest -q
```

## Endpoints de categorías

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/v1/catalog/categories` | Crear categoría o subcategoría (201) |
| `PATCH` | `/api/v1/catalog/categories/{id}` | Editar nombre, descripción, orden o padre (200) |
| `DELETE` | `/api/v1/catalog/categories/{id}` | Desactivación lógica (200) |
| `GET` | `/api/v1/catalog/categories` | Árbol de categorías activas (200) |

Documentación funcional: [`docs/HU-07_gestion_de_categorias.md`](docs/HU-07_gestion_de_categorias.md).

## Endpoints de productos

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/v1/catalog/products` | Crear producto en borrador (201) |
| `PATCH` | `/api/v1/catalog/products/{id}` | Editar producto propio (200) |
| `POST` | `/api/v1/catalog/products/{id}/submit-review` | Enviar a revisión (200) |
| `PATCH` | `/api/v1/catalog/products/{id}/archive` | Archivar y retirar de la vitrina (200) |
| `PATCH` | `/api/v1/catalog/products/{id}/reactivate` | Publicar o enviar a revisión (200) |
| `GET` | `/api/v1/catalog/products` | Vitrina de productos publicados (200) |
| `GET` | `/api/v1/catalog/products/{id}` | Detalle de un producto (200) |

El autor se obtiene del token (`Authorization: Bearer <token>`) o, mientras se
integra la autenticación, de las cabeceras `X-Actor-Id` / `X-Actor-Roles`.
Documentación funcional y ciclo de vida:
[`docs/HU-08_producto_creacion_edicion_y_ciclo_de_vida.md`](docs/HU-08_producto_creacion_edicion_y_ciclo_de_vida.md).

## Endpoints de medios del producto

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/v1/catalog/products/{id}/media` | Cargar imagen o video (201) |
| `DELETE` | `/api/v1/catalog/products/{id}/media/{mediaId}` | Eliminar medio y reordenar (200) |

Documentación funcional:
[`docs/HU-09_medios_del_producto.md`](docs/HU-09_medios_del_producto.md).

Todas las respuestas usan el sobre `{ "message", "data", "success" }`.
