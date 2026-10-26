## [HU-18] Reseñas y calificaciones

> **Módulo:** Comunidad  
> **Submódulo(s):** SUB-22, SUB-23  
> **Funciones:** FUN-54, FUN-55, FUN-56, FUN-57  
> **Actor:** Consumidor  
> **Prioridad:** Media · **Puntos:** 5

### 📖 Historia de Usuario

**Dado** un consumidor que compró un producto digital,  
**Para** que comparta su experiencia y ayude a otros compradores a decidir,  
**Que** publique una reseña con calificación, consulte reseñas y vea la calificación promedio.

### 🎯 Beneficio esperado

La comunidad accede a opiniones verificadas y los productores reciben retroalimentación útil.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-54 | Comunidad | Reseñas | Publicar reseña | PRC-54 |
| FUN-55 | Comunidad | Reseñas | Consultar reseñas | PRC-55 |
| FUN-56 | Comunidad | Calificaciones | Calcular calificación promedio | PRC-56 |
| FUN-57 | Comunidad | Calificaciones | Consultar calificación | PRC-57 |

### 🔁 Flujo Esperado

- El consumidor abre el producto comprado.
- El sistema verifica la compra o licencia.
- El consumidor escribe la reseña y asigna una calificación de 1 a 5.
- La reseña se guarda y se publica review.created.
- El promedio del producto se recalcula y se muestra.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] POST /api/v1/community/products/{id}/reviews exige compra o licencia si COMU-04 está activo.
- [ ] Solo se permite una reseña por usuario y producto si COMU-03 está activo.
- [ ] La calificación debe estar entre 1 y 5 según COMU-01.
- [ ] El texto respeta la longitud COMU-02.
- [ ] GET /reviews devuelve reseñas visibles paginadas.
- [ ] GET /rating devuelve promedio y total.
- [ ] Una reseña duplicada responde 409 y una sin compra 403.

#### 2. 📆 Estructura de la información

- [ ] La reseña contiene id, productId, userId, calificacion, texto y fecha.
- [ ] La calificación contiene promedio, total y distribución.
- [ ] Los errores indican compra faltante, duplicado o rango inválido.

```json
{
  "message": "Reseña publicada correctamente.",
  "data": {
    "id": "rev_300",
    "productId": "prod_100",
    "userId": "usr_001",
    "calificacion": 5,
    "texto": "Excelente calidad y entrega inmediata.",
    "fecha": "2026-10-25T18:00:00Z"
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- La compra se valida contra Comercio por API interna.
- El promedio se calcula con agregación y se cachea.
- Las reseñas ofensivas pueden reportarse a Control de publicaciones.
- El texto se sanitiza antes de mostrarse.

### 🚀 Endpoints

- `POST /api/v1/community/products/{id}/reviews`
- `GET /api/v1/community/products/{id}/reviews`
- `GET /api/v1/community/products/{id}/rating`

### 🧪 Requisitos de Pruebas

#### Caso 1: Reseña válida

- **Precondición:** Compra confirmada.
- **Acción:** POST /reviews.
- **Resultado esperado:** 201 y promedio actualizado.

#### Caso 2: Sin compra

- **Precondición:** Usuario sin licencia.
- **Acción:** POST /reviews.
- **Resultado esperado:** 403.

#### Caso 3: Reseña duplicada

- **Precondición:** Reseña existente del mismo usuario y producto.
- **Acción:** POST otra reseña.
- **Resultado esperado:** 409.

#### Caso 4: Calificación inválida

- **Precondición:** Compra confirmada.
- **Acción:** POST con calificación 6.
- **Resultado esperado:** 400.

#### Caso 5: Consulta de promedio

- **Precondición:** Reseñas publicadas.
- **Acción:** GET /rating.
- **Resultado esperado:** 200 con promedio y total.

### ✅ Definición de Hecho

- [ ] Reseñas y calificaciones documentadas.
- [ ] Validación de compra y duplicados probada.
- [ ] Promedio y distribución verificados.
- [ ] Sanitización de texto activa.
- [ ] Evento review.created publicado.

---

