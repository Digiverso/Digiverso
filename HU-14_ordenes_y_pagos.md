## [HU-14] Órdenes y pagos

> **Módulo:** Comercio  
> **Submódulo(s):** SUB-15, SUB-16  
> **Funciones:** FUN-40, FUN-41, FUN-42, FUN-43  
> **Actor:** Consumidor  
> **Prioridad:** Alta · **Puntos:** 8

### 📖 Historia de Usuario

**Dado** un consumidor autenticado que desea comprar un producto digital,  
**Para** que obtenga el producto de forma segura y sin cobros duplicados,  
**Que** cree una orden, pague en la pasarela y reciba la confirmación.

### 🎯 Beneficio esperado

El comprador completa la compra con confianza y la plataforma evita fraudes, duplicados y órdenes inconsistentes.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-40 | Comercio | Órdenes | Crear orden | PRC-40 |
| FUN-41 | Comercio | Órdenes | Cancelar orden | PRC-41 |
| FUN-42 | Comercio | Pagos | Procesar pago | PRC-42 |
| FUN-43 | Comercio | Pagos | Confirmar pago | PRC-43 |

### 🔁 Flujo Esperado

- El consumidor selecciona el producto y crea la orden.
- El sistema valida producto publicado, comprador y ausencia de licencia previa.
- Calcula precio y comisión y crea la orden pendiente.
- El consumidor es enviado a la pasarela con idempotencia.
- El webhook confirma el pago y la orden queda pagada.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] POST /api/v1/commerce/orders valida producto publicado, comprador autenticado y licencia previa.
- [ ] Una compra duplicada responde 409.
- [ ] La orden calcula precio, comisión COM-01 y neto COM-02.
- [ ] La orden pendiente vence en COM-05 minutos.
- [ ] POST /checkout usa Idempotency-Key.
- [ ] POST /payments/webhook valida firma, monto, referencia e idempotencia.
- [ ] Un webhook inválido responde 400 y no cambia la orden.
- [ ] POST /cancel solo aplica a órdenes no pagadas.

#### 2. 📆 Estructura de la información

- [ ] La orden contiene id, productId, compradorId, precio, comision, netoProductor, estado y fecha.
- [ ] La confirmación contiene ordenId, estado, licenciaId y fechaPago.
- [ ] Los errores usan el sobre estándar.

```json
{
  "message": "Orden creada correctamente.",
  "data": {
    "id": "ord_500",
    "productId": "prod_100",
    "compradorId": "usr_001",
    "precio": 45000,
    "comision": 6750,
    "netoProductor": 38250,
    "estado": "pendiente",
    "fechaCreacion": "2026-10-25T18:00:00Z"
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- La comisión se calcula con aritmética decimal.
- La idempotencia evita órdenes y cobros duplicados.
- El webhook se valida con firma HMAC.
- La licencia se emite después del commit del pago.

### 🚀 Endpoints

- `POST /api/v1/commerce/orders`
- `POST /api/v1/commerce/orders/{id}/checkout`
- `POST /api/v1/commerce/payments/webhook`
- `POST /api/v1/commerce/orders/{id}/cancel`

### 🧪 Requisitos de Pruebas

#### Caso 1: Compra exitosa

- **Precondición:** Producto publicado y comprador sin licencia.
- **Acción:** Crear orden, checkout y webhook aprobado.
- **Resultado esperado:** Orden pagada y licencia emitida.

#### Caso 2: Compra duplicada

- **Precondición:** Licencia activa del mismo producto.
- **Acción:** Crear otra orden.
- **Resultado esperado:** 409.

#### Caso 3: Webhook inválido

- **Precondición:** Orden pendiente.
- **Acción:** Enviar firma incorrecta.
- **Resultado esperado:** 400 y orden sin cambios.

#### Caso 4: Cancelar orden pendiente

- **Precondición:** Orden pendiente.
- **Acción:** POST /cancel.
- **Resultado esperado:** 200 y reserva liberada.

#### Caso 5: Producto no disponible

- **Precondición:** Producto archivado.
- **Acción:** Crear orden.
- **Resultado esperado:** 409 o 404.

### ✅ Definición de Hecho

- [ ] Órdenes y pagos documentados.
- [ ] Cálculo de comisión probado.
- [ ] Idempotencia y firma verificadas.
- [ ] Licencia y evento order.paid comprobados.
- [ ] Cancelación de orden probada.

---

