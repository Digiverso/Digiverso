## [HU-16] Comisiones, ventas y liquidaciones

> **Módulo:** Comercio  
> **Submódulo(s):** SUB-20  
> **Funciones:** FUN-48, FUN-49, FUN-50, FUN-51, FUN-52  
> **Actor:** Productor  
> **Prioridad:** Alta · **Puntos:** 8

### 📖 Historia de Usuario

**Dado** un productor que vende productos digitales,  
**Para** que conozca sus ingresos, comisiones y fechas de pago,  
**Que** consulte ventas y liquidaciones y reciba una notificación por cada venta.

### 🎯 Beneficio esperado

El productor tiene transparencia sobre sus ingresos y la plataforma cumple el acuerdo comercial del 85 %.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-48 | Comercio | Comisiones y liquidaciones | Calcular comisión | PRC-48 |
| FUN-49 | Comercio | Comisiones y liquidaciones | Registrar venta | PRC-49 |
| FUN-50 | Comercio | Comisiones y liquidaciones | Consultar ventas | PRC-50 |
| FUN-51 | Comercio | Comisiones y liquidaciones | Consultar liquidaciones | PRC-51 |
| FUN-52 | Comercio | Comisiones y liquidaciones | Notificar venta al productor | PRC-52 |

### 🔁 Flujo Esperado

- El pago de una orden se confirma.
- El sistema calcula comisión 15 % y neto 85 %.
- Registra la venta y acumula el saldo del productor.
- El productor consulta ventas y liquidaciones.
- Recibe una notificación de venta con el monto neto.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] La comisión se calcula con COM-01 y el neto con COM-02.
- [ ] La venta se registra solo para órdenes pagadas.
- [ ] GET /producer/sales muestra ventas, comisiones y totales.
- [ ] GET /producer/payouts muestra liquidaciones y estados.
- [ ] Una liquidación se genera después de COM-10 días y con mínimo COM-11.
- [ ] Order.paid genera notificación al productor.
- [ ] Los montos usan aritmética decimal y moneda COM-03.

#### 2. 📆 Estructura de la información

- [ ] La venta contiene ventaId, ordenId, productId, monto, comision, neto y fecha.
- [ ] La liquidación contiene payoutId, periodo, total y estado.
- [ ] La notificación contiene producto, monto neto y fecha.

```json
{
  "message": "Ventas consultadas correctamente.",
  "data": {
    "items": [
      { "ventaId": "sale_200", "producto": "Pack de ilustraciones", "monto": 45000, "comision": 6750, "neto": 38250, "fecha": "2026-10-25T18:05:00Z" }
    ],
    "totalNeto": 38250
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- Los movimientos de venta son inmutables.
- Las liquidaciones se generan por job programado.
- La notificación se envía después del commit de la venta.
- Los reportes permiten exportar a CSV.

### 🚀 Endpoints

- `GET /api/v1/commerce/producer/sales`
- `GET /api/v1/commerce/producer/payouts`
- `EVENTO order.paid`

### 🧪 Requisitos de Pruebas

#### Caso 1: Cálculo 15/85

- **Precondición:** Venta de 45.000 COP.
- **Acción:** Registrar venta.
- **Resultado esperado:** Comisión 6.750 y neto 38.250.

#### Caso 2: Venta sin pago

- **Precondición:** Orden pendiente.
- **Acción:** Intentar registrar venta.
- **Resultado esperado:** 409 y sin registro.

#### Caso 3: Consulta de ventas

- **Precondición:** Productor con ventas.
- **Acción:** GET /producer/sales.
- **Resultado esperado:** 200 con totales.

#### Caso 4: Liquidación mínima

- **Precondición:** Saldo menor a COM-11.
- **Acción:** Generar liquidación.
- **Resultado esperado:** No se genera y se informa.

#### Caso 5: Notificación de venta

- **Precondición:** Venta registrada.
- **Acción:** Consultar bandeja del productor.
- **Resultado esperado:** Notificación con monto neto.

### ✅ Definición de Hecho

- [ ] Cálculo de comisión probado.
- [ ] Ventas y liquidaciones documentadas.
- [ ] Notificación de venta verificada.
- [ ] Reportes y exportación probados.
- [ ] Auditoría de movimientos activa.

---

