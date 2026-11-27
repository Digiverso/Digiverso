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

### 🔁 Flujo esperado

- HU-19 publica `user.followed` y HU-18 publica `review.created` después del
  commit de la interacción.
- El consumidor normaliza el evento, resuelve al destinatario y descarta
  auto-notificaciones.
- Consulta COMU-11 y las preferencias AUT-10 (canales y tipos) antes de entregar.
- Renderiza la plantilla versionada con el nombre público del emisor y un
  detalle acotado; nunca incluye correos, ids ni el texto de la reseña.
- Guarda la notificación en la bandeja (retención AUT-11), registra canal y
  estado de cada entrega y reintenta el correo sin duplicar la notificación.

### ✅ Criterios de aceptación

#### 1. Estructura y lógica del servicio

- [x] FUN-63 consume `user.followed` y `review.created`.
- [x] Respeta COMU-11 y los canales AUT-10.
- [x] No genera notificación al mismo usuario que realizó la acción.
- [x] La notificación se guarda en la bandeja con retención AUT-11.
- [x] Un fallo de entrega se reintenta (`NOTIFICATION_MAX_RETRIES`) sin duplicar la notificación.
- [x] El mensaje no expone datos privados (sanitiza nombre, quita correo/URL/markup y nunca copia `texto`).

#### 2. Estructura de la información

- [x] La notificación contiene `id`, `tipo`, `emisor`, `mensaje`, `leida` y `fecha`.
- [x] La entrega registra canal y estado.
- [x] La bandeja permite marcar como leída (mismo endpoint de HU-05).

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

### 🔧 Notas técnicas

- **Contrato `user.followed`**: `seguidorId` (o `actorId`/`userId`),
  `seguidoId` (o `destinatarioId`) y, opcionalmente, `seguidorNombre` e `id`.
- **Contrato `review.created`**: `userId`, `productId`, `calificacion`, `id` y,
  opcionalmente, `productorId`. Si no viene el productor, se resuelve desde el
  producto; el texto de la reseña nunca se usa en el mensaje.
- **COMU-11**: interruptor global `COMU_11_ENABLED` (por defecto `true`),
  complementado por los tipos `nuevo_seguidor` y `nueva_resena` de AUT-10 en
  las preferencias de cada usuario.
- **Idempotencia**: clave `hu20:<evento>:<usuario>:<idEvento>`; un replay del
  evento devuelve la notificación original. `NotificationService` de HU-05
  comparte el mismo repositorio de bandeja y entregas.
- **Plantillas versionadas**: `PLANTILLAS_VERSIONADAS` en
  `app/domain/community_notifications.py` (versión 1). Se incrementa la versión
  sin alterar las notificaciones ya guardadas.
- **Retención AUT-11**: se aplica al consultar la bandeja, igual que en HU-05.
- **Aislamiento de merges**: las clases nuevas viven en `app/domain/`,
  `app/repository/`, `app/services/`, `app/api/` y `docs/`; el único enganche
  es `router.include_router(...)` al final de `app/api/v1/notifications.py`.
  No se tocan `main.py`, `core/config.py`, `repository/events.py` ni
  `api/schemas.py`, que son modificados por HU-18 y HU-19.

### 🚀 Endpoints y eventos

| Método / evento | Ruta / topic | Descripción |
|---|---|---|
| `EVENTO` | `user.followed` | Consumido por `CommunityNotificationConsumer.procesar_evento`. |
| `EVENTO` | `review.created` | Consumido por el mismo servicio; notifica al productor. |
| `GET` | `/api/v1/users/me/notifications` | Bandeja general de HU-05 (incluye estas notificaciones). |
| `GET` | `/api/v1/users/me/notifications/comunidad` | Bandeja de comunidad con `emisor`, paginada (200/401). |
| `PATCH` | `/api/v1/users/me/notifications/{id}/read` | Marcar como leída, heredado de HU-05 (200/401/404). |

`CommunityNotificationConsumer.consumir_lote(bus.events())` permite drenar los
eventos ya publicados por el bus en memoria sin acoplar el productor al
consumidor.

### 🧪 Pruebas

`tests/test_community_notifications_api.py` cubre:

1. Nuevo seguidor: notificación en bandeja con emisor y mensaje de la plantilla.
2. COMU-11 desactivado: no se genera notificación.
3. Auto-notificación: el emisor no recibe su propia interacción.
4. Reintento sin duplicado: un fallo temporal deja una sola notificación.
5. Reseña nueva: notificación al productor con la calificación, sin el texto.
6. Preferencias AUT-10: tipo desactivado y canales habilitados.
7. Retención AUT-11 y lectura de la notificación.

### ✅ Definición de hecho

- [x] Eventos y notificación documentados.
- [x] Preferencias y auto-notificación probadas.
- [x] Idempotencia verificada.
- [x] Plantillas versionadas.
- [x] Retención AUT-11 aplicada.
