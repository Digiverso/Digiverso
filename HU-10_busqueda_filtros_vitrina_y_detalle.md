## [HU-10] Búsqueda, filtros, vitrina y detalle

> **Módulo:** Catálogo  
> **Submódulo(s):** SUB-11, SUB-12  
> **Funciones:** FUN-28, FUN-29, FUN-30, FUN-31  
> **Actor:** Visitante, Consumidor  
> **Prioridad:** Alta · **Puntos:** 5

### 📖 Historia de Usuario

**Dado** un visitante o consumidor que busca un producto digital,  
**Para** que encuentre rápidamente una opción que cumpla sus intereses y edad,  
**Que** busque por texto, filtre por categoría, edad y precio, y consulte vitrina y detalle.

### 🎯 Beneficio esperado

El comprador descubre la oferta con menos fricción y la plataforma aumenta la conversión.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-28 | Catálogo | Búsqueda y filtros | Buscar productos | PRC-28 |
| FUN-29 | Catálogo | Búsqueda y filtros | Filtrar productos | PRC-29 |
| FUN-30 | Catálogo | Vitrina y detalle | Consultar vitrina | PRC-30 |
| FUN-31 | Catálogo | Vitrina y detalle | Consultar detalle del producto | PRC-31 |

### 🔁 Flujo Esperado

- El visitante escribe un término de búsqueda.
- El sistema consulta solo productos publicados.
- El visitante aplica filtros de categoría, edad, precio y orden.
- El sistema devuelve la vitrina agrupada por categoría.
- El visitante abre el detalle y ve autor, medios, calificación y condiciones.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] GET /api/v1/catalog/products?q= busca solo productos publicados.
- [ ] Los filtros validan categoría, edad CAT-03, precio CAT-01 y orden permitido.
- [ ] La paginación tiene límite máximo y orden estable.
- [ ] GET /api/v1/catalog/showcase agrupa productos publicados por categoría.
- [ ] GET /api/v1/catalog/products/{id} devuelve detalle solo si está publicado o si el usuario tiene licencia.
- [ ] Un producto no publicado responde 404 para visitantes.

#### 2. 📆 Estructura de la información

- [ ] La búsqueda devuelve items, total, pagina y tamanioPagina.
- [ ] Cada item contiene id, nombre, precio, autor, categoría, calificación y miniatura.
- [ ] El detalle incluye medios, descripción, edad y licencia del usuario si existe.

```json
{
  "message": "Búsqueda realizada correctamente.",
  "data": {
    "items": [
      { "id": "prod_100", "nombre": "Pack de ilustraciones", "precio": 45000, "autor": "Ana Torres", "calificacion": 4.8 }
    ],
    "total": 1,
    "pagina": 1,
    "tamanioPagina": 20
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- La búsqueda usa un índice con sinónimos y tolerancia a errores.
- Los filtros se combinan con AND y el orden por relevancia o fecha.
- La vitrina se cachea por categoría.
- El detalle no expone datos privados del productor.

### 🚀 Endpoints

- `GET /api/v1/catalog/products?q=`
- `GET /api/v1/catalog/products`
- `GET /api/v1/catalog/showcase`
- `GET /api/v1/catalog/products/{id}`

### 🧪 Requisitos de Pruebas

#### Caso 1: Búsqueda por texto

- **Precondición:** Producto publicado con el término.
- **Acción:** GET /products?q=ilustracion.
- **Resultado esperado:** 200 con el producto.

#### Caso 2: Filtro por edad

- **Precondición:** Productos con edades distintas.
- **Acción:** GET con edad=12.
- **Resultado esperado:** 200 solo con productos compatibles.

#### Caso 3: Producto no publicado

- **Precondición:** Producto en revisión.
- **Acción:** GET /products/{id} como visitante.
- **Resultado esperado:** 404.

#### Caso 4: Vitrina por categoría

- **Precondición:** Categoría con productos publicados.
- **Acción:** GET /showcase.
- **Resultado esperado:** 200 agrupado por categoría.

#### Caso 5: Paginación

- **Precondición:** Más de 20 productos.
- **Acción:** GET con pagina=2.
- **Resultado esperado:** 200 con el siguiente conjunto.

### ✅ Definición de Hecho

- [ ] Búsqueda, filtros, vitrina y detalle documentados.
- [ ] Solo productos publicados visibles.
- [ ] Paginación y orden probados.
- [ ] Índice de búsqueda actualizado.
- [ ] Datos privados excluidos.

---

