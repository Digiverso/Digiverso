## [HU-07] Gestión de categorías

> **Módulo:** Catálogo  
> **Submódulo(s):** SUB-08  
> **Funciones:** FUN-17, FUN-18, FUN-19, FUN-20  
> **Actor:** Administrador  
> **Prioridad:** Media · **Puntos:** 5

### 📖 Historia de Usuario

**Dado** un administrador que organiza la oferta del marketplace,  
**Para** que compradores y productores encuentren los productos en categorías claras,  
**Que** cree, edite, desactive y consulte el árbol de categorías.

### 🎯 Beneficio esperado

La oferta queda organizada, evita duplicidades y mejora la navegación y la búsqueda.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-17 | Catálogo | Categorías | Crear categoría | PRC-17 |
| FUN-18 | Catálogo | Categorías | Editar categoría | PRC-18 |
| FUN-19 | Catálogo | Categorías | Desactivar categoría | PRC-19 |
| FUN-20 | Catálogo | Categorías | Consultar categorías | PRC-20 |

### 🔁 Flujo Esperado

- El administrador crea una categoría o subcategoría.
- El sistema valida unicidad, longitud y jerarquía.
- El administrador edita nombre o descripción.
- El administrador desactiva una categoría sin eliminar su historial.
- Los visitantes consultan el árbol de categorías activas.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] POST /api/v1/catalog/categories valida nombre único por padre y longitud CAT-17.
- [ ] No se permiten ciclos en la jerarquía.
- [ ] PATCH /api/v1/catalog/categories/{id} actualiza nombre, descripción o padre con validación.
- [ ] DELETE /api/v1/catalog/categories/{id} es lógico y no elimina productos históricos.
- [ ] Una categoría con productos activos no se desactiva sin reasignarlos.
- [ ] GET /api/v1/catalog/categories devuelve solo categorías activas.

#### 2. 📆 Estructura de la información

- [ ] La categoría contiene id, nombre, padreId, estado y orden.
- [ ] El árbol se devuelve con hijos anidados.
- [ ] Los errores de duplicidad responden 409.

```json
{
  "message": "Categoría creada correctamente.",
  "data": {
    "id": "cat_010",
    "nombre": "Ilustración digital",
    "padreId": "cat_001",
    "estado": "activa"
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- La jerarquía se almacena con materialized path o closure table.
- La desactivación es lógica para conservar trazabilidad.
- Se invalida la cache del árbol al cambiar una categoría.
- Los nombres se normalizan para evitar duplicados por mayúsculas o tildes.

### 🚀 Endpoints

- `POST /api/v1/catalog/categories`
- `PATCH /api/v1/catalog/categories/{id}`
- `DELETE /api/v1/catalog/categories/{id}`
- `GET /api/v1/catalog/categories`

### 🧪 Requisitos de Pruebas

#### Caso 1: Crear categoría

- **Precondición:** Administrador y nombre único.
- **Acción:** POST /catalog/categories.
- **Resultado esperado:** 201 con categoría activa.

#### Caso 2: Nombre duplicado

- **Precondición:** Categoría existente con el mismo padre.
- **Acción:** POST con el mismo nombre.
- **Resultado esperado:** 409.

#### Caso 3: Jerarquía cíclica

- **Precondición:** Categoría padre e hijo existentes.
- **Acción:** Mover el padre bajo su hijo.
- **Resultado esperado:** 400 y sin cambios.

#### Caso 4: Desactivar con productos

- **Precondición:** Categoría con productos activos.
- **Acción:** DELETE /categories/{id}.
- **Resultado esperado:** 409 y exige reasignación.

#### Caso 5: Consultar árbol

- **Precondición:** Categorías activas.
- **Acción:** GET /catalog/categories.
- **Resultado esperado:** 200 con árbol anidado.

### ✅ Definición de Hecho

- [ ] CRUD de categorías documentado.
- [ ] Validación de duplicados y ciclos probada.
- [ ] Desactivación lógica y reasignación verificadas.
- [ ] Cache del árbol invalidada.
- [ ] Auditoría de cambios activa.

---

