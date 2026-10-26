## [HU-19] Seguimiento, feed, intereses y recomendaciones

> **Módulo:** Comunidad  
> **Submódulo(s):** SUB-24, SUB-25, SUB-26  
> **Funciones:** FUN-58, FUN-59, FUN-60, FUN-61, FUN-62  
> **Actor:** Consumidor  
> **Prioridad:** Media · **Puntos:** 8

### 📖 Historia de Usuario

**Dado** un consumidor que quiere descubrir productores y productos afines,  
**Para** que reciba novedades y recomendaciones relevantes sin buscar manualmente,  
**Que** siga y deje de seguir productores, consulte su feed, configure intereses y reciba recomendaciones.

### 🎯 Beneficio esperado

El comprador descubre contenido de su interés y los productores amplían su audiencia.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-58 | Comunidad | Seguimiento | Seguir usuario | PRC-58 |
| FUN-59 | Comunidad | Seguimiento | Dejar de seguir usuario | PRC-59 |
| FUN-60 | Comunidad | Feed | Consultar feed de seguidos | PRC-60 |
| FUN-61 | Comunidad | Intereses y recomendaciones | Configurar intereses | PRC-61 |
| FUN-62 | Comunidad | Intereses y recomendaciones | Consultar recomendaciones | PRC-62 |

### 🔁 Flujo Esperado

- El consumidor sigue a un productor.
- El sistema valida que no sea auto-seguimiento y el límite COMU-05.
- El consumidor consulta el feed de los productores seguidos.
- Configura sus categorías de interés hasta COMU-08.
- El sistema recomienda productos excluyendo comprados y propios.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] POST /users/{id}/follow no permite auto-seguimiento y respeta COMU-05.
- [ ] DELETE /users/{id}/follow elimina la relación y actualiza contadores.
- [ ] GET /feed/following muestra solo productos publicados de los seguidos, paginado con COMU-07.
- [ ] PUT /community/me/interests valida categorías existentes y el límite COMU-08.
- [ ] GET /feed/recommended excluye productos comprados y propios.
- [ ] Las recomendaciones respetan COMU-09 y el orden COMU-10.
- [ ] Un usuario inexistente responde 404.

#### 2. 📆 Estructura de la información

- [ ] El feed contiene items, total y pagina.
- [ ] Cada item contiene producto, autor, precio y fecha.
- [ ] Las recomendaciones contienen producto, motivo y puntuación.

```json
{
  "message": "Feed consultado correctamente.",
  "data": {
    "items": [
      { "productId": "prod_100", "nombre": "Pack de ilustraciones", "autor": "Ana Torres", "precio": 45000 }
    ],
    "total": 1,
    "pagina": 1
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- El feed se construye con un fan-out híbrido y cache.
- Las recomendaciones usan intereses y señales de compra.
- El auto-seguimiento se rechaza en dominio.
- Los contadores se actualizan de forma eventual.

### 🚀 Endpoints

- `POST /api/v1/community/users/{id}/follow`
- `DELETE /api/v1/community/users/{id}/follow`
- `GET /api/v1/community/feed/following`
- `PUT /api/v1/community/me/interests`
- `GET /api/v1/community/feed/recommended`

### 🧪 Requisitos de Pruebas

#### Caso 1: Seguir productor

- **Precondición:** Usuario autenticado y límite disponible.
- **Acción:** POST /follow.
- **Resultado esperado:** 201 con relación creada.

#### Caso 2: Auto-seguimiento

- **Precondición:** Usuario autenticado.
- **Acción:** POST /follow con su propio id.
- **Resultado esperado:** 400.

#### Caso 3: Feed de seguidos

- **Precondición:** Al menos un seguido con productos publicados.
- **Acción:** GET /feed/following.
- **Resultado esperado:** 200 con productos.

#### Caso 4: Intereses excedidos

- **Precondición:** Usuario con COMU-08 intereses.
- **Acción:** PUT /interests con otro.
- **Resultado esperado:** 409.

#### Caso 5: Recomendaciones

- **Precondición:** Usuario con intereses e historial.
- **Acción:** GET /feed/recommended.
- **Resultado esperado:** 200 sin productos comprados ni propios.

### ✅ Definición de Hecho

- [ ] Seguimiento, feed, intereses y recomendaciones documentados.
- [ ] Límites y auto-seguimiento probados.
- [ ] Exclusión de comprados y propios verificada.
- [ ] Cache de feed invalidada.
- [ ] Contadores actualizados.

---

