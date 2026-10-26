## [HU-20] Notificaciones de comunidad

> **Módulo:** Comunidad  
> **Submódulo(s):** SUB-27  
> **Funciones:** FUN-63  
> **Actor:** Consumidor, Productor  
> **Prioridad:** Baja · **Puntos:** 3

### 📖 Historia de Usuario

**Dado** un usuario que recibe seguidores o reseñas,  
**Para** que se entere de las interacciones relevantes sin revisar manualmente,  
**Que** reciba notificaciones de comunidad respetando sus preferencias.

### 🎯 Beneficio esperado

El usuario mantiene engagement y la plataforma evita notificaciones invasivas.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-63 | Comunidad | Notificaciones de comunidad | Notificar interacción de comunidad | PRC-63 |

### 🔁 Flujo Esperado

- Ocurre un evento user.followed o review.created.
- El sistema verifica las preferencias del usuario.
- Construye el mensaje con el emisor y el contenido.
- Entrega la notificación por los canales habilitados.
- La notificación queda en la bandeja.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] FUN-63 consume user.followed y review.created.
- [ ] Respeta COMU-11 y los canales AUT-10.
- [ ] No genera notificación al mismo usuario que realizó la acción.
- [ ] La notificación se guarda en la bandeja con retención AUT-11.
- [ ] Un fallo de entrega se reintenta sin duplicar la notificación.
- [ ] El mensaje no expone datos privados.

#### 2. 📆 Estructura de la información

- [ ] La notificación contiene id, tipo, emisor, mensaje, leida y fecha.
- [ ] La entrega registra canal y estado.
- [ ] La bandeja permite marcar como leída.

```json
{
  "message": "Notificación de comunidad generada.",
  "data": {
    "id": "ntf_200",
    "tipo": "nuevo_seguidor",
    "emisor": "Ana Torres",
    "mensaje": "Ana Torres comenzó a seguirte.",
    "leida": false,
    "fecha": "2026-10-25T18:00:00Z"
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- La notificación se genera después del commit del evento.
- Se usa una clave de idempotencia por evento y usuario.
- Las preferencias se consultan antes de entregar.
- El contenido se renderiza con plantillas versionadas.

### 🚀 Endpoints

- `EVENTO user.followed`
- `EVENTO review.created`
- `GET /api/v1/users/me/notifications`

### 🧪 Requisitos de Pruebas

#### Caso 1: Nuevo seguidor

- **Precondición:** Usuario con notificaciones activas.
- **Acción:** Seguir al usuario.
- **Resultado esperado:** Notificación en bandeja.

#### Caso 2: Preferencia desactivada

- **Precondición:** Usuario con COMU-11=false.
- **Acción:** Recibir un seguimiento.
- **Resultado esperado:** No se genera notificación.

#### Caso 3: Auto-notificación

- **Precondición:** Usuario sigue a otro.
- **Acción:** Procesar evento.
- **Resultado esperado:** No se notifica al emisor.

#### Caso 4: Reintento sin duplicado

- **Precondición:** Fallo temporal de entrega.
- **Acción:** Reintentar el evento.
- **Resultado esperado:** Una sola notificación.

#### Caso 5: Reseña nueva

- **Precondición:** Reseña publicada.
- **Acción:** Procesar review.created.
- **Resultado esperado:** Notificación al productor.

### ✅ Definición de Hecho

- [ ] Eventos y notificación documentados.
- [ ] Preferencias y auto-notificación probadas.
- [ ] Idempotencia verificada.
- [ ] Plantillas versionadas.
- [ ] Retención AUT-11 aplicada.

---

