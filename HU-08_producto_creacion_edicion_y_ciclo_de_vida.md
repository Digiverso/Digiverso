## [HU-08] Producto: creación, edición y ciclo de vida

> **Módulo:** Catálogo  
> **Submódulo(s):** SUB-09  
> **Funciones:** FUN-21, FUN-22, FUN-23, FUN-24, FUN-25  
> **Actor:** Productor  
> **Prioridad:** Alta · **Puntos:** 8

### 📖 Historia de Usuario

**Dado** un productor autenticado que desea vender una producción digital propia,  
**Para** que publique su producto con reglas claras y controle su disponibilidad,  
**Que** cree, edite, envíe a revisión, archive y reactive sus productos.

### 🎯 Beneficio esperado

El productor publica con autonomía y la plataforma conserva reglas de autoría, precio, edad y estado.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-21 | Catálogo | Producto | Crear producto | PRC-21 |
| FUN-22 | Catálogo | Producto | Editar producto | PRC-22 |
| FUN-23 | Catálogo | Producto | Enviar producto a revisión | PRC-23 |
| FUN-24 | Catálogo | Producto | Archivar producto | PRC-24 |
| FUN-25 | Catálogo | Producto | Reactivar producto | PRC-25 |

### 🔁 Flujo Esperado

- El productor crea un producto en borrador.
- El sistema valida autoría, precio mínimo, edad, categorías y longitudes.
- El productor edita el producto mientras esté en borrador, rechazado o publicado.
- El productor envía el producto a revisión cuando está completo.
- El producto puede archivarse y reactivarse según su estado y cambios.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] POST /api/v1/catalog/products valida autoría, precio CAT-01, edad CAT-03, nombre CAT-11, descripción CAT-12 y categorías CAT-13.
- [ ] El precio menor a 3.500 COP responde 422.
- [ ] Un productor solo edita sus propios productos; otro responde 403.
- [ ] POST /submit-review exige al menos CAT-09 imágenes y cambia a en_revision.
- [ ] PATCH /archive cambia a archivado y retira de la vitrina sin afectar licencias.
- [ ] PATCH /reactivate envía a revisión si hubo cambios; si no, publica.
- [ ] Las transiciones de estado inválidas responden 409.

#### 2. 📆 Estructura de la información

- [ ] El producto contiene id, nombre, descripción, precio, edadMinima, edadMaxima, categorías, estado, autorId y medios.
- [ ] La creación devuelve el producto en estado borrador.
- [ ] Las transiciones devuelven el estado resultante y la fecha.

```json
{
  "message": "Producto creado en borrador.",
  "data": {
    "id": "prod_100",
    "nombre": "Pack de ilustraciones",
    "precio": 45000,
    "moneda": "COP",
    "edadMinima": 0,
    "edadMaxima": 99,
    "estado": "borrador",
    "autorId": "usr_010"
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- El autor se toma del token, no del cuerpo de la petición.
- Las reglas de contenido se validan en la capa de dominio.
- El producto archivado conserva licencias y datos históricos.
- Los cambios de estado se auditan con actor y fecha.

### 🚀 Endpoints

- `POST /api/v1/catalog/products`
- `PATCH /api/v1/catalog/products/{id}`
- `POST /api/v1/catalog/products/{id}/submit-review`
- `PATCH /api/v1/catalog/products/{id}/archive`
- `PATCH /api/v1/catalog/products/{id}/reactivate`

### 🧪 Requisitos de Pruebas

#### Caso 1: Crear producto válido

- **Precondición:** Productor autenticado y datos válidos.
- **Acción:** POST /catalog/products.
- **Resultado esperado:** 201 en borrador.

#### Caso 2: Precio bajo el mínimo

- **Precondición:** Productor autenticado.
- **Acción:** POST con precio 3000.
- **Resultado esperado:** 422 y sin crear.

#### Caso 3: Editar producto ajeno

- **Precondición:** Productor autenticado.
- **Acción:** PATCH de otro autor.
- **Resultado esperado:** 403.

#### Caso 4: Enviar sin medios

- **Precondición:** Producto sin imágenes.
- **Acción:** POST /submit-review.
- **Resultado esperado:** 422 y sigue en borrador.

#### Caso 5: Archivar con licencias

- **Precondición:** Producto publicado con licencias.
- **Acción:** PATCH /archive.
- **Resultado esperado:** 200 y licencias siguen vigentes.

#### Caso 6: Reactivar con cambios

- **Precondición:** Producto archivado y modificado.
- **Acción:** PATCH /reactivate.
- **Resultado esperado:** 200 y estado en_revision.

### ✅ Definición de Hecho

- [ ] Ciclo de vida del producto documentado.
- [ ] Validaciones de precio, edad, autoría y estados probadas.
- [ ] Licencias conservadas al archivar.
- [ ] Auditoría de transiciones activa.
- [ ] Pruebas de autoría y estados inválidos aprobadas.

---

