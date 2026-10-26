## [HU-11] Control de publicaciones

> **Módulo:** Catálogo  
> **Submódulo(s):** SUB-13  
> **Funciones:** FUN-32, FUN-33, FUN-34, FUN-38  
> **Actor:** Administrador  
> **Prioridad:** Alta · **Puntos:** 8

### 📖 Historia de Usuario

**Dado** un administrador responsable de verificar el cumplimiento de las políticas,  
**Para** que solo se publiquen productos propios, seguros y con derechos de autor claros,  
**Que** consulte la cola de revisión, apruebe o rechace con justificación y notifique al productor.

### 🎯 Beneficio esperado

La plataforma protege a compradores y productores, reduce riesgos legales y mantiene la calidad del catálogo.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-32 | Catálogo | Control de publicaciones | Consultar cola de revisión | PRC-32 |
| FUN-33 | Catálogo | Control de publicaciones | Aprobar publicación | PRC-33 |
| FUN-34 | Catálogo | Control de publicaciones | Rechazar publicación | PRC-34 |
| FUN-38 | Catálogo | Control de publicaciones | Notificar resultado de revisión | PRC-38 |

### 🔁 Flujo Esperado

- El administrador consulta la cola de productos en revisión.
- El sistema ordena por antigüedad y muestra el expediente.
- El administrador verifica autoría, edad, derechos, contenido y funciones.
- Aprueba o rechaza con checklist y observación.
- El sistema cambia el estado, indexa o mantiene rechazado y notifica al productor.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] GET /api/v1/catalog/publication-control/queue requiere rol administrador.
- [ ] La cola muestra solo productos en_revision y ordena por fecha de envío.
- [ ] PATCH /approve exige checklist completo y cambia a publicado.
- [ ] PATCH /reject exige motivo CAT-14 y observación; cambia a rechazado.
- [ ] Un administrador no puede revisar un producto propio.
- [ ] La decisión publica product.reviewed y notifica al productor.
- [ ] Toda decisión queda auditada con evidencia.

#### 2. 📆 Estructura de la información

- [ ] La cola contiene producto, autor, fechaEnvio, medios y políticas aplicables.
- [ ] La aprobación devuelve productoId, estado y fechaPublicacion.
- [ ] El rechazo devuelve productoId, estado, motivo y observación.

```json
{
  "message": "Publicación aprobada correctamente.",
  "data": {
    "productoId": "prod_100",
    "estado": "publicado",
    "fechaPublicacion": "2026-10-25T18:00:00Z",
    "notificado": true
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- El checklist se guarda como evidencia de la revisión.
- La aprobación indexa el producto para búsqueda.
- El rechazo permite corregir y reenviar.
- La notificación se envía después del commit del estado.

### 🚀 Endpoints

- `GET /api/v1/catalog/publication-control/queue`
- `PATCH /api/v1/catalog/publication-control/{id}/approve`
- `PATCH /api/v1/catalog/publication-control/{id}/reject`
- `EVENTO product.reviewed`

### 🧪 Requisitos de Pruebas

#### Caso 1: Aprobar publicación

- **Precondición:** Producto en revisión y checklist completo.
- **Acción:** PATCH /approve.
- **Resultado esperado:** 200, publicado e indexado.

#### Caso 2: Rechazar sin motivo

- **Precondición:** Producto en revisión.
- **Acción:** PATCH /reject sin motivo.
- **Resultado esperado:** 400 y sin cambios.

#### Caso 3: Acceso no administrador

- **Precondición:** Productor autenticado.
- **Acción:** GET /queue.
- **Resultado esperado:** 403.

#### Caso 4: Revisar producto propio

- **Precondición:** Administrador que también es autor.
- **Acción:** PATCH /approve.
- **Resultado esperado:** 403 por separación de funciones.

#### Caso 5: Notificación al productor

- **Precondición:** Decisión registrada.
- **Acción:** Consultar bandeja del productor.
- **Resultado esperado:** Notificación con decisión y motivo.

### ✅ Definición de Hecho

- [ ] Cola, aprobación y rechazo documentados.
- [ ] Checklist y evidencias persistidos.
- [ ] Separación de funciones probada.
- [ ] Evento product.reviewed publicado.
- [ ] Notificación al productor verificada.

---

