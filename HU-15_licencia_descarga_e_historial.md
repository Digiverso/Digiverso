## [HU-15] Licencia, descarga e historial

> **Módulo:** Comercio  
> **Submódulo(s):** SUB-17, SUB-18, SUB-19  
> **Funciones:** FUN-44, FUN-45, FUN-46, FUN-47  
> **Actor:** Consumidor  
> **Prioridad:** Alta · **Puntos:** 8

### 📖 Historia de Usuario

**Dado** un consumidor con una compra pagada,  
**Para** que acceda a su producto digital y consulte sus compras cuando lo necesite,  
**Que** reciba una licencia de uso, descargue el archivo y consulte su historial.

### 🎯 Beneficio esperado

El comprador obtiene acceso inmediato y seguro, y la plataforma controla la distribución del contenido.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-44 | Comercio | Licencias | Emitir licencia de uso | PRC-44 |
| FUN-45 | Comercio | Licencias | Consultar licencia | PRC-45 |
| FUN-46 | Comercio | Descargas | Descargar producto | PRC-46 |
| FUN-47 | Comercio | Historial de compras | Consultar historial de compras | PRC-47 |

### 🔁 Flujo Esperado

- El pago confirmado genera una licencia de uso sin edición.
- El consumidor consulta la licencia y sus condiciones.
- Solicita la descarga y el sistema valida la licencia.
- Se genera una URL firmada y temporal.
- El consumidor consulta su historial de compras y licencias.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] La licencia se emite solo para una orden pagada.
- [ ] La licencia permite uso sin edición y no permite reventa.
- [ ] GET /licenses/{id} devuelve estado y condiciones.
- [ ] GET /purchases/{id}/download exige licencia activa.
- [ ] La URL de descarga vence en COM-08 minutos.
- [ ] El límite de descargas respeta COM-09.
- [ ] Un producto archivado sigue disponible para licencias vigentes.
- [ ] GET /purchases pagina y ordena por fecha.

#### 2. 📆 Estructura de la información

- [ ] La licencia contiene id, productoId, compradorId, estado, condiciones y fecha.
- [ ] La descarga devuelve url, expiraEn y nombreArchivo.
- [ ] El historial contiene compras, licencias y estados.

```json
{
  "message": "Licencia consultada correctamente.",
  "data": {
    "id": "lic_900",
    "productoId": "prod_100",
    "compradorId": "usr_001",
    "estado": "activa",
    "condiciones": "Uso personal, sin edición ni reventa",
    "fechaEmision": "2026-10-25T18:05:00Z"
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- La URL firmada se genera con expiración corta.
- Las descargas se auditan por usuario, producto e IP.
- La licencia se emite en la misma transacción lógica del pago.
- El archivo se sirve desde S3 con control de acceso.

### 🚀 Endpoints

- `GET /api/v1/commerce/licenses/{id}`
- `GET /api/v1/commerce/purchases/{id}/download`
- `GET /api/v1/commerce/purchases`

### 🧪 Requisitos de Pruebas

#### Caso 1: Consultar licencia

- **Precondición:** Compra pagada.
- **Acción:** GET /licenses/{id}.
- **Resultado esperado:** 200 con licencia activa.

#### Caso 2: Descarga con licencia

- **Precondición:** Licencia activa.
- **Acción:** GET /download.
- **Resultado esperado:** 200 con URL firmada.

#### Caso 3: Descarga sin licencia

- **Precondición:** Usuario sin compra.
- **Acción:** GET /download.
- **Resultado esperado:** 403.

#### Caso 4: URL expirada

- **Precondición:** URL con más de COM-08 minutos.
- **Acción:** Acceder a la URL.
- **Resultado esperado:** 403 o 410.

#### Caso 5: Historial

- **Precondición:** Compras pagadas.
- **Acción:** GET /purchases.
- **Resultado esperado:** 200 paginado.

#### Caso 6: Producto archivado

- **Precondición:** Licencia vigente y producto archivado.
- **Acción:** Descargar.
- **Resultado esperado:** 200, acceso conservado.

### ✅ Definición de Hecho

- [ ] Licencia, descarga e historial documentados.
- [ ] URL firmada y expiración probadas.
- [ ] Control de acceso verificado.
- [ ] Auditoría de descargas activa.
- [ ] Licencias conservadas al archivar.

---

