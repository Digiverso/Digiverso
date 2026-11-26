## [HU-04] Roles y permisos

> **Módulo:** Autenticación  
> **Submódulo(s):** SUB-05  
> **Funciones:** FUN-09, FUN-10, FUN-11  
> **Actor:** Administrador  
> **Prioridad:** Alta · **Puntos:** 5

### 📖 Historia de Usuario

**Dado** un administrador responsable de la seguridad de la plataforma,  
**Para** que cada usuario acceda solo a las funciones que le corresponden,  
**Que** asigne roles permitidos y el sistema resuelva y valide permisos en cada operación.

### 🎯 Beneficio esperado

La plataforma aplica mínimo privilegio y reduce accesos indebidos a publicación, administración y datos de otros usuarios.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-09 | Autenticación | Roles y permisos | Asignar rol | PRC-09 |
| FUN-10 | Autenticación | Roles y permisos | Consultar permisos | PRC-10 |
| FUN-11 | Autenticación | Roles y permisos | Validar permisos | PRC-11 |

### 🔁 Flujo esperado

- El administrador selecciona un usuario y un rol permitido por AUT-09.
- El sistema valida el permiso `admin.users.roles.write`, el rol y la cuenta.
- La asignación se aplica, es idempotente y queda auditada.
- El usuario consulta sus permisos efectivos.
- Cada operación protegida valida rol, recurso y acción antes de ejecutarse.
- Una operación denegada responde 403 y registra auditoría.

### ✅ Criterios de aceptación

#### 1. Estructura y lógica del servicio

- [x] `POST /api/v1/admin/users/{id}/roles` solo acepta roles de AUT-09.
- [x] Solo un administrador puede asignar roles y no puede degradar al último administrador.
- [x] `GET /api/v1/users/me/permissions` devuelve permisos efectivos del usuario.
- [x] La validación de permisos se aplica antes de ejecutar la operación (`PermissionValidator`).
- [x] Una operación sin permiso responde 403, no modifica datos y se audita.
- [x] Todo cambio de rol queda auditado (`rol_asignado`).

#### 2. Estructura de la información

- [x] La respuesta de permisos contiene `rol`, `permisos` y `recursos`.
- [x] La asignación devuelve `usuarioId`, `rolAnterior` y `rolNuevo`.
- [x] Los errores de autorización usan el sobre estándar `message` / `data` / `success`.

```json
{
  "message": "Permisos consultados correctamente.",
  "data": {
    "usuarioId": "usr_001",
    "rol": "productor",
    "permisos": [
      "users.profile.read",
      "users.profile.write",
      "catalog.product.create",
      "catalog.product.edit",
      "commerce.sales.read"
    ],
    "recursos": ["users.profile", "catalog.product", "commerce.sales"]
  },
  "success": true
}
```

### 🔧 Notas técnicas

- **AUT-09 se mantiene separada del catálogo de HU-06.** El modelo de HU-06 es
  entero y no admite una lista de roles; por eso `AUT-09` vive en
  `app/domain/roles.py` y no se agrega a `PARAMETROS_AUTENTICACION`.
- **Roles permitidos:** `consumidor`, `productor`, `administrador`.
- **Permisos resueltos por rol:**
  - `consumidor`: lectura y escritura de su perfil.
  - `productor`: perfil + creación/edición de productos + lectura de ventas.
  - `administrador`: todos los anteriores, más categorías, roles, parámetros de
    autenticación, permisos y ventas.
- **Scopes del token:** `accessToken` incluye `scopes` derivados del rol vigente
  al emitirlo, pero son informativos. La decisión final la toma el servicio
  consultando el repositorio, de modo que un cambio de rol surte efecto sin
  esperar a que expire el token.
- **Doble origen del principal:** para no romper las HU del catálogo, el
  endpoint de administración acepta sesión RS256 (HU-01), token de actor HMAC o
  las cabeceras `X-Actor-Id` / `X-Actor-Roles`. Si se envía `Authorization`,
  una credencial inválida **nunca** cae al administrador por defecto. Una sesión
  válida de consumidor no puede elevarse añadiendo cabeceras de roles.
- **Último administrador:** no se puede degradar la única cuenta con rol
  `administrador` (409).
- **Idempotencia:** repetir la misma asignación responde 200 y no genera un
  segundo evento `rol_asignado`.
- **Auditoría:** se registran `rol_asignado`, `rol_asignacion_rechazada` y
  `permiso_denegado` en el repositorio de autenticación, con actor, IP y fecha.

### 🚀 Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/v1/admin/users/{id}/roles` | Asignar rol permitido por AUT-09 (200/400/401/403/404/409) |
| `GET` | `/api/v1/users/me/permissions` | Consultar permisos efectivos (200/401) |
| `INTERNO` | `PermissionValidator` / `ensure_permiso()` | Validar rol, recurso y acción antes de ejecutar |

Ejemplo de asignación:

```json
{
  "message": "Rol asignado correctamente.",
  "data": {
    "usuarioId": "usr_001",
    "rolAnterior": "consumidor",
    "rolNuevo": "productor"
  },
  "success": true
}
```

### ⚠️ Errores

| Código HTTP | `data.codigo` | Situación |
|---:|---|---|
| 400 | `rol_no_permitido` | El rol no está en AUT-09 |
| 401 | `credenciales_invalidas` | Falta una credencial válida |
| 403 | `permiso_denegado` | El principal no tiene `admin.users.roles.write` |
| 404 | `usuario_no_encontrado` | No existe la cuenta indicada |
| 409 | `ultimo_administrador` | Se intenta degradar al último administrador |

### 🧪 Pruebas

`tests/test_roles_permissions_api.py` cubre:

1. Asignación válida: 200, rol actualizado y auditoría.
2. Rol no permitido: 400, sin cambios y auditoría de rechazo.
3. Consumidor con cabeceras: 403, sin cambios.
4. Sesión de consumidor con cabeceras falsas: 403 (la sesión manda).
5. Token inválido: 401 (sin escalada al administrador por defecto).
6. Último administrador: 409 y rol conservado.
7. Idempotencia: una sola auditoría para dos asignaciones iguales.
8. Consulta de permisos de productor y sin token.
9. Scopes del token derivados del rol vigente.
10. Validación interna: administrador permitido y consumidor denegado/auditado.

### ✅ Definición de hecho

- [x] Roles y permisos documentados.
- [x] Pruebas de mínimo privilegio aprobadas.
- [x] Auditoría de asignaciones activa.
- [x] Protección del último administrador verificada.
- [x] Scopes y validación interna alineados.
