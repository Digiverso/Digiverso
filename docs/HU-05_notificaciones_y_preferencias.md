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

### 🔁 Flujo esperado

- El usuario configura canales y tipos de notificación (AUT-10).
- Un evento de cuenta genera una notificación.
- La cola entrega por los canales habilitados y registra intentos.
- La notificación se guarda en la bandeja con retención AUT-11.
- El usuario consulta su bandeja y marca una notificación como leída.

### ✅ Criterios de aceptación

#### 1. Estructura y lógica del servicio

- [x] `PUT /api/v1/users/me/notification-preferences` acepta solo canales de AUT-10.
- [x] Las notificaciones críticas de seguridad se envían aunque el usuario desactive canales no críticos.
- [x] `GET /api/v1/users/me/notifications` devuelve solo notificaciones del usuario autenticado.
- [x] `PATCH /api/v1/users/me/notifications/{id}/read` valida pertenencia y es idempotente.
- [x] La retención respeta AUT-11 (30 días por defecto, configurable por `AUT_11_RETENTION_DAYS`).
- [x] La bandeja se pagina y ordena por fecha descendente.

#### 2. Estructura de la información

- [x] La notificación contiene `id`, `tipo`, `mensaje`, `canal`, `leida` y `fecha`.
- [x] La preferencia contiene `canales` y `tipos` activos.
- [x] Una notificación ajena responde 404 sin revelar datos.

```json
{
  "message": "Notificaciones consultadas correctamente.",
  "data": {
    "items": [
      {
        "id": "ntf_100",
        "tipo": "cuenta_verificada",
        "mensaje": "Tu cuenta fue verificada.",
        "canal": "in_app",
        "leida": false,
        "fecha": "2026-10-25T18:00:00Z"
      }
    ],
    "pagina": 1,
    "total": 1
  },
  "success": true
}
```

### 🔧 Notas técnicas

- **AUT-10** se mantiene fuera del catálogo entero de HU-06 (que solo admite
  valores `int`). Vive en `app/domain/notifications.py`.
  - Canales: `email`, `in_app`, `push`.
  - Tipos: `cuenta_verificada`, `perfil_actualizado`, `producto_publicado`,
    `nuevo_seguidor`, `nueva_resena`, `password_reset`, `cuenta_bloqueada`,
    `rol_asignado`, `login_sospechoso`.
- **AUT-11**: retención de 30 días. La limpieza se ejecuta al escribir y al
  consultar la bandeja, sin necesidad de un proceso externo.
- **Plantillas versionadas:** `NotificationTemplate` renderiza por tipo y
  canal; el mensaje guardado en la bandeja corresponde al canal `in_app` (o al
  primero habilitado).
- **Cola y reintentos:** cada entrega registra `estado`, `intentos` y fecha. Un
  fallo de correo se reintenta hasta `NOTIFICATION_MAX_RETRIES` (3) sin
  duplicar la notificación.
- **Criticidad:** `password_reset`, `cuenta_bloqueada`, `rol_asignado` y
  `login_sospechoso` se envían por `email` e `in_app` aunque el usuario haya
  desactivado esos canales o tipos.
- **Idempotencia:** `notificar_evento()` acepta `clave_idempotencia`; `AuthService`
  la usa para `cuenta_verificada` y `password_reset`.
- **Aislamiento:** la bandeja filtra siempre por `cuenta_id` del token de sesión;
  un identificador ajeno y uno inexistente devuelven el mismo 404.

### 🚀 Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `PUT` | `/api/v1/users/me/notification-preferences` | Guardar canales y tipos (200/400/401) |
| `GET` | `/api/v1/users/me/notifications` | Bandeja paginada (200/401) |
| `PATCH` | `/api/v1/users/me/notifications/{id}/read` | Marcar como leída (200/401/404) |

### ⚠️ Errores

| Código HTTP | `data.codigo` | Situación |
|---:|---|---|
| 400 | `canal_no_permitido` | Canal fuera de AUT-10 o lista vacía |
| 400 | `tipo_no_permitido` | Tipo fuera de AUT-10 |
| 401 | `credenciales_invalidas` | Token ausente, inválido o sin sesión activa |
| 404 | `notificacion_no_encontrada` | Notificación inexistente o ajena |

### 🧪 Pruebas

`tests/test_notifications_api.py` cubre:

1. Preferencias válidas guardadas.
2. Canal no permitido: 400 y sin cambios.
3. Tipo no permitido: 400 y sin cambios.
4. Bandeja propia, paginada y ordenada descendentemente.
5. Lectura idempotente.
6. Notificación ajena: 404 y sin cambios.
7. Notificación crítica no silenciada (fuerza email + in_app).
8. Notificación no crítica silenciada por tipo.
9. Idempotencia por clave de evento.
10. Retención AUT-11.
11. Reintentos de entrega registrados sin duplicar la notificación.

### ✅ Definición de hecho

- [x] Preferencias, bandeja y lectura documentadas.
- [x] Pruebas de pertenencia y canales aprobadas.
- [x] Plantillas y cola de envío verificadas.
- [x] Retención AUT-11 configurada.
- [x] Notificaciones críticas excluidas del silenciamiento.
