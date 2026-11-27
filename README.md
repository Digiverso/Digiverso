# Digiverso API

API del marketplace Digiverso. Incluye los módulos **Autenticación**
(HU-01, HU-02, perfil HU-03/FUN-07 a FUN-08, roles HU-04, notificaciones HU-05
y parametrización HU-06/FUN-16), **Catálogo · Categorías**
(HU-07, FUN-17 a FUN-20), **Catálogo · Productos** (HU-08, FUN-21 a FUN-25),
**Catálogo · Medios del producto** (HU-09, FUN-26 y FUN-27),
**Catálogo · Búsqueda, vitrina y detalle** (HU-10, FUN-28 a FUN-31) y
**Catálogo · Control de publicaciones** (HU-11, FUN-32 a FUN-34 y FUN-38).

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

## Endpoints de perfil

Requieren `Authorization: Bearer <accessToken>` obtenido en `POST /api/v1/auth/login`.

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v1/users/me` | Consultar el perfil propio (200) |
| `PATCH` | `/api/v1/users/me` | Editar nombre, biografía o foto (200) |
| `GET` | `/api/v1/users/me/permissions` | Consultar permisos efectivos (200) |
| `PUT` | `/api/v1/users/me/notification-preferences` | Configurar canales y tipos (200/400) |
| `GET` | `/api/v1/users/me/notifications` | Consultar bandeja paginada (200) |
| `PATCH` | `/api/v1/users/me/notifications/{id}/read` | Marcar como leída (200/404) |

Documentación funcional: [`docs/HU-03_perfil_de_usuario.md`](docs/HU-03_perfil_de_usuario.md).

## Roles y permisos

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/v1/admin/users/{id}/roles` | Asignar rol permitido por AUT-09 (200/400/403/404/409) |

Acepta sesión RS256, token de actor o `X-Actor-Id` / `X-Actor-Roles`; requiere
permiso `admin.users.roles.write`. Documentación funcional:
[`docs/HU-04_roles_y_permisos.md`](docs/HU-04_roles_y_permisos.md).

## Notificaciones y preferencias

Los canales y tipos se validan contra AUT-10; la bandeja aplica retención AUT-11
(30 días por defecto). Las notificaciones críticas de seguridad no se silencian.
Documentación funcional:
[`docs/HU-05_notificaciones_y_preferencias.md`](docs/HU-05_notificaciones_y_preferencias.md).

## Endpoints de parámetros de autenticación

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v1/admin/auth/parameters` | Parámetros vigentes, versión y validaciones (200) |
| `PUT` | `/api/v1/admin/auth/parameters` | Validar y guardar una nueva versión (200) |
| `GET` | `/api/v1/admin/auth/parameters/history` | Historial de versiones inmutables (200) |
| `GET` | `/api/v1/admin/auth/parameters/history/{version}` | Detalle de una versión (200/404) |

Requieren rol `administrador` o el alcance `admin.auth.parameters.write`.
Documentación funcional:
[`docs/HU-06_parametrizacion_de_autenticacion.md`](docs/HU-06_parametrizacion_de_autenticacion.md).

## Endpoints de parámetros de comunidad

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v1/admin/community/parameters` | Parámetros vigentes, versión y validaciones (200) |
| `PUT` | `/api/v1/admin/community/parameters` | Validar y guardar una nueva versión (200/400/403) |
| `GET` | `/api/v1/admin/community/parameters/history` | Historial de versiones inmutables (200) |
| `GET` | `/api/v1/admin/community/parameters/history/{version}` | Detalle de una versión (200/404) |

Requieren rol `administrador` o el alcance `admin.community.parameters.write`.
Documentación funcional:
[`docs/HU-21_parametrizacion_de_comunidad.md`](docs/HU-21_parametrizacion_de_comunidad.md).

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
| `GET` | `/api/v1/catalog/products` | Búsqueda paginada de publicados con filtros (200) |
| `GET` | `/api/v1/catalog/products/{id}` | Detalle público/licenciado (200) o 404 |

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

## Endpoints de búsqueda y vitrina

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v1/catalog/products?q=&categoria=&edad=&precioMin=&precioMax=&orden=&pagina=&tamanioPagina=` | Buscar y filtrar solo productos publicados (200) |
| `GET` | `/api/v1/catalog/showcase` | Vitrina agrupada por categoría, cacheada (200) |

Documentación funcional:
[`docs/HU-10_busqueda_filtros_vitrina_y_detalle.md`](docs/HU-10_busqueda_filtros_vitrina_y_detalle.md).

## Endpoints de control de publicaciones

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v1/catalog/publication-control/queue` | Cola de revisión ordenada por antigüedad (200/403) |
| `PATCH` | `/api/v1/catalog/publication-control/{id}/approve` | Aprobar con checklist completo (200/400/403/404/409) |
| `PATCH` | `/api/v1/catalog/publication-control/{id}/reject` | Rechazar con motivo CAT-14 y observación (200/400/403/404/409) |

Solo administradores; un administrador no puede revisar sus propios productos.
Cada decisión queda auditada con evidencia y publica el evento `product.reviewed`,
además de notificar al productor (FUN-38). Documentación funcional:
[`docs/HU-11_control_de_publicaciones.md`](docs/HU-11_control_de_publicaciones.md).

Todas las respuestas usan el sobre `{ "message", "data", "success" }`.
