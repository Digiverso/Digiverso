# Digiverso API

API del marketplace Digiverso. Actualmente incluye el módulo **Catálogo · Categorías**
(HU-07, FUN-17 a FUN-20).

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

Todas las respuestas usan el sobre `{ "message", "data", "success" }`.
La documentación funcional detallada está en [`docs/HU-07_gestion_de_categorias.md`](docs/HU-07_gestion_de_categorias.md).
