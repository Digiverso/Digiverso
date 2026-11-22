# [HU-07] Gestión de categorías — implementación

**Módulo:** Catálogo · **Submódulo:** SUB-08 · **Funciones:** FUN-17, FUN-18, FUN-19, FUN-20
**Actor:** Administrador

## Endpoints

Base: `/api/v1/catalog/categories`. Todas las respuestas —correctas e incorrectas—
usan el sobre `message` / `data` / `success`.

### POST `/categories` (FUN-17)

Crea una categoría raíz (`padreId: null/omitido`) o una subcategoría.

```json
{
  "nombre": "Ilustración digital",
  "descripcion": "Obras creadas con herramientas digitales",
  "padreId": "cat_001",
  "orden": 1
}
```

Respuesta `201`:

```json
{
  "message": "Categoría creada correctamente.",
  "data": {
    "id": "cat_010",
    "nombre": "Ilustración digital",
    "descripcion": "Obras creadas con herramientas digitales",
    "padreId": "cat_001",
    "estado": "activa",
    "orden": 1,
    "hijos": []
  },
  "success": true
}
```

### PATCH `/categories/{id}` (FUN-18)

Actualiza solo los campos enviados. Campos: `nombre`, `descripcion`, `padreId`, `orden`.
Enviar `"padreId": null` mueve la categoría a la raíz. Al mover un nodo se
reescriben las rutas materializadas de todo su subárbol en la misma transacción.

### DELETE `/categories/{id}` (FUN-19)

Desactivación lógica (`estado: "inactiva"`, `eliminado_en`). No elimina la
categoría ni sus productos históricos. Si hay productos activos en la categoría
o en sus descendientes, responde `409`; hay que reasignarlos primero.

### GET `/categories` (FUN-20)

Devuelve únicamente categorías activas, anidadas en `hijos` y ordenadas por
`orden`, nombre normalizado e identificador. El árbol se sirve desde caché en
memoria.

## Reglas de negocio

| Regla | Resultado |
|---|---|
| Nombre único por padre, comparando sin mayúsculas ni tildes | `409 CATEGORY_DUPLICATE` |
| Longitud CAT-17 (por defecto 2–80 caracteres) | `422 CATEGORY_INVALID` |
| Padre inexistente o inactivo | `400 CATEGORY_INVALID_PARENT` |
| Moverse a sí misma o a un descendiente | `400 CATEGORY_CYCLE` (sin cambios) |
| Desactivar con productos activos en el subárbol | `409 CATEGORY_ACTIVE_PRODUCTS` |
| Categoría inexistente | `404 CATEGORY_NOT_FOUND` |
| Sin permiso `catalog.category.write` | `403 CATALOG_FORBIDDEN` |

La unicidad se evalúa entre **todas** las categorías, incluidas las inactivas,
para conservar la trazabilidad y evitar ambigüedades al reutilizar nombres.

## Decisiones técnicas

- **Jerarquía:** materialized path en `categories.ruta` (`/cat_001/cat_002/`).
  La detección de ciclos es un prefijo sobre esa ruta.
- **Cache:** `InMemoryCategoryTreeCache`, invalidada por el servicio en
  crear/editar/desactivar. Implementa el protocolo `CategoryTreeCache`, por lo
  que puede sustituirse por Redis u otra implementación.
- **Auditoría:** tabla `audit_log` con actor, roles, fecha y valores
  anterior/posterior en cada escritura. Consultable desde
  `SQLiteAuditRepository.list_for_entity`.
- **Productos:** el esquema crea una tabla `productos` mínima (`categoria_id`,
  `activo`) como contrato con HU-08 para verificar la regla de reasignación.
- **Actor:** hasta integrar HU-01/HU-02/HU-04, las peticiones pueden enviar
  `X-Actor-Id` y `X-Actor-Roles` (separados por comas). Sin cabeceras se usa
  `usr_admin` con rol `administrador`, salvo si `REQUIRE_EXPLICIT_ACTOR=true`.

### Parámetros configurables

| Variable | Valor por defecto | Uso |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./dev.db` | Ubicación de la base de datos |
| `CAT_17_MIN_LENGTH` | `2` | Longitud mínima CAT-17 |
| `CAT_17_MAX_LENGTH` | `80` | Longitud máxima CAT-17 |
| `CAT_17_DESCRIPTION_MAX` | `500` | Longitud máxima de descripción |
| `REQUIRE_EXPLICIT_ACTOR` | `false` | Exigir cabeceras de actor |

El valor numérico de CAT-17 no estaba definido en el repositorio; se fija en
80 caracteres y queda sobreescribible por configuración.

## Pruebas

```bash
pytest -q
```

Cubre: creación, duplicidad normalizada, longitud CAT-17, ciclos, edición con
movimiento de subárbol, desactivación con/sin productos, árbol anidado,
invalidación de caché, auditoría, permisos y jerarquía inválida.
