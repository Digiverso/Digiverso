## [HU-05] Notificaciones y preferencias

> **Módulo:** Autenticación  
> **Submódulo(s):** SUB-06  
> **Funciones:** FUN-12, FUN-13, FUN-14, FUN-15  
> **Actor:** Consumidor, Productor  
> **Prioridad:** Media · **Puntos:** 5

### 📖 Historia de Usuario

**Dado** un usuario que realiza compras, publica o recibe interacciones,  
**Para** que se entere de los eventos relevantes sin recibir notificaciones innecesarias,  
**Que** configure sus canales, consulte su bandeja y marque notificaciones como leídas.

### 🎯 Beneficio esperado

El usuario mantiene el control de su comunicación y la plataforma entrega mensajes oportunos por el canal correcto.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-12 | Autenticación | Notificaciones y preferencias | Notificar evento de cuenta | PRC-12 |
| FUN-13 | Autenticación | Notificaciones y preferencias | Configurar preferencias de notificación | PRC-13 |
| FUN-14 | Autenticación | Notificaciones y preferencias | Consultar bandeja de notificaciones | PRC-14 |
| FUN-15 | Autenticación | Notificaciones y preferencias | Marcar notificación como leída | PRC-15 |

### 🔁 Flujo Esperado

- El usuario configura canales y tipos de notificación.
- El sistema valida las opciones contra AUT-10.
- Un evento de cuenta genera una notificación.
- La notificación se entrega por los canales habilitados y se guarda en la bandeja.
- El usuario consulta su bandeja y marca una notificación como leída.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] PUT /api/v1/users/me/notification-preferences acepta solo canales de AUT-10.
- [ ] Las notificaciones críticas de seguridad se envían aunque el usuario desactive canales no críticos.
- [ ] GET /api/v1/users/me/notifications devuelve solo las notificaciones del usuario autenticado.
- [ ] PATCH /api/v1/users/me/notifications/{id}/read valida pertenencia y es idempotente.
- [ ] La retención de notificaciones respeta AUT-11.
- [ ] La bandeja se pagina y ordena por fecha descendente.

#### 2. 📆 Estructura de la información

- [ ] La notificación contiene id, tipo, mensaje, canal, leida y fecha.
- [ ] La preferencia contiene canales y tipos activos.
- [ ] Los errores de pertenencia responden 403 o 404 sin revelar datos.

```json
{
  "message": "Notificaciones consultadas correctamente.",
  "data": {
    "items": [
      { "id": "ntf_100", "tipo": "cuenta_verificada", "mensaje": "Tu cuenta fue verificada.", "leida": false, "fecha": "2026-10-25T18:00:00Z" }
    ],
    "pagina": 1,
    "total": 1
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- Las plantillas de notificación se versionan por tipo y canal.
- El envío usa una cola y registra reintentos.
- Las notificaciones críticas de seguridad no se silencian.
- La bandeja usa retención AUT-11 y limpieza programada.

### 🚀 Endpoints

- `PUT /api/v1/users/me/notification-preferences`
- `GET /api/v1/users/me/notifications`
- `PATCH /api/v1/users/me/notifications/{id}/read`

### 🧪 Requisitos de Pruebas

#### Caso 1: Preferencia válida

- **Precondición:** Usuario autenticado.
- **Acción:** PUT con canales permitidos.
- **Resultado esperado:** 200 y preferencias guardadas.

#### Caso 2: Canal no permitido

- **Precondición:** Usuario autenticado.
- **Acción:** PUT con canal desconocido.
- **Resultado esperado:** 400 y sin cambios.

#### Caso 3: Bandeja propia

- **Precondición:** Usuario con notificaciones.
- **Acción:** GET /users/me/notifications.
- **Resultado esperado:** 200 solo con sus notificaciones.

#### Caso 4: Marcar leída

- **Precondición:** Notificación propia no leída.
- **Acción:** PATCH /read.
- **Resultado esperado:** 200 y leida=true.

#### Caso 5: Notificación ajena

- **Precondición:** Notificación de otro usuario.
- **Acción:** PATCH /read.
- **Resultado esperado:** 403 o 404 y sin cambios.

### ✅ Definición de Hecho

- [ ] Preferencias, bandeja y lectura documentadas.
- [ ] Pruebas de pertenencia y canales aprobadas.
- [ ] Plantillas y cola de envío verificadas.
- [ ] Retención AUT-11 configurada.
- [ ] Notificaciones críticas excluidas del silenciamiento.

---

