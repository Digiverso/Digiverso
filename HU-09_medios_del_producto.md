## [HU-09] Medios del producto

> **Módulo:** Catálogo  
> **Submódulo(s):** SUB-10  
> **Funciones:** FUN-26, FUN-27  
> **Actor:** Productor  
> **Prioridad:** Media · **Puntos:** 3

### 📖 Historia de Usuario

**Dado** un productor con un producto en borrador o publicado,  
**Para** que el comprador vea el contenido con imágenes y videos de calidad,  
**Que** cargue y elimine medios del producto respetando formatos, tamaños y cantidad.

### 🎯 Beneficio esperado

La ficha del producto es atractiva y confiable, y la plataforma evita archivos inválidos o maliciosos.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-26 | Catálogo | Medios del producto | Cargar medio | PRC-26 |
| FUN-27 | Catálogo | Medios del producto | Eliminar medio | PRC-27 |

### 🔁 Flujo Esperado

- El productor selecciona una imagen o video.
- El sistema valida formato, tamaño y cantidad permitida.
- El archivo se almacena y se asocia al producto.
- El productor puede eliminar un medio propio.
- El sistema reordena los medios restantes.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] POST /api/v1/catalog/products/{id}/media acepta solo formatos CAT-05 y CAT-07.
- [ ] Cada imagen respeta CAT-06 y cada video CAT-08.
- [ ] El producto no supera CAT-10 medios.
- [ ] Solo el autor puede cargar o eliminar medios.
- [ ] DELETE /media/{mediaId} es lógico y reordena los restantes.
- [ ] El archivo se escanea antes de publicarse.

#### 2. 📆 Estructura de la información

- [ ] El medio contiene id, tipo, url, orden y estado.
- [ ] La carga devuelve el medio asociado y el total de medios.
- [ ] Los errores indican formato, tamaño o cantidad.

```json
{
  "message": "Medio cargado correctamente.",
  "data": {
    "id": "med_010",
    "productoId": "prod_100",
    "tipo": "imagen",
    "url": "https://cdn.digiverso.com/products/prod_100/med_010.webp",
    "orden": 1
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- Se valida el tipo real del archivo con firma binaria.
- Las imágenes se optimizan y convierten a WebP.
- Los videos se procesan de forma asíncrona.
- El acceso a la carga requiere autoría y estado editable.

### 🚀 Endpoints

- `POST /api/v1/catalog/products/{id}/media`
- `DELETE /api/v1/catalog/products/{id}/media/{mediaId}`

### 🧪 Requisitos de Pruebas

#### Caso 1: Cargar imagen válida

- **Precondición:** Producto propio y archivo permitido.
- **Acción:** POST /media.
- **Resultado esperado:** 201 con medio asociado.

#### Caso 2: Formato no permitido

- **Precondición:** Archivo GIF.
- **Acción:** POST /media.
- **Resultado esperado:** 400.

#### Caso 3: Archivo demasiado grande

- **Precondición:** Imagen mayor a CAT-06.
- **Acción:** POST /media.
- **Resultado esperado:** 413.

#### Caso 4: Eliminar medio ajeno

- **Precondición:** Producto de otro autor.
- **Acción:** DELETE /media/{id}.
- **Resultado esperado:** 403.

#### Caso 5: Superar máximo de medios

- **Precondición:** Producto con CAT-10 medios.
- **Acción:** POST otro medio.
- **Resultado esperado:** 409.

### ✅ Definición de Hecho

- [ ] Carga y eliminación documentadas.
- [ ] Validación de formato, tamaño y cantidad probada.
- [ ] Escaneo de archivos activo.
- [ ] Reordenamiento verificado.
- [ ] Autoría validada.

---

