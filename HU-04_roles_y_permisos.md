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

### 🔁 Flujo Esperado

- El administrador selecciona un usuario y un rol permitido.
- El sistema valida el rol contra AUT-09 y registra la asignación.
- El usuario consulta sus permisos efectivos.
- Cada operación protegida valida rol, recurso y acción.
- Una operación no autorizada se deniega y se audita.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] POST /api/v1/admin/users/{id}/roles solo acepta roles de AUT-09.
- [ ] Solo un administrador puede asignar roles y no puede degradar al último administrador.
- [ ] GET /api/v1/users/me/permissions devuelve permisos efectivos del usuario.
- [ ] La validación de permisos se aplica antes de ejecutar la operación.
- [ ] Una operación sin permiso responde 403 y no modifica datos.
- [ ] Todo cambio de rol queda auditado.

#### 2. 📆 Estructura de la información

- [ ] La respuesta de permisos contiene rol, permisos y recursos.
- [ ] La asignación devuelve usuarioId, rol anterior y rol nuevo.
- [ ] Los errores de autorización usan el sobre estándar.

```json
{
  "message": "Permisos consultados correctamente.",
  "data": {
    "usuarioId": "usr_001",
    "rol": "productor",
    "permisos": ["catalog.product.create", "catalog.product.edit", "commerce.sales.read"]
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- Los permisos se resuelven por rol y por política de recurso.
- El token incluye scopes, pero la decisión final se valida en el servicio.
- La asignación de roles es idempotente y auditada.
- Se protege la cuenta del último administrador.

### 🚀 Endpoints

- `POST /api/v1/admin/users/{id}/roles`
- `GET /api/v1/users/me/permissions`
- `INTERNO Middleware de autorización`

### 🧪 Requisitos de Pruebas

#### Caso 1: Asignación válida

- **Precondición:** Administrador y rol permitido.
- **Acción:** POST /admin/users/{id}/roles.
- **Resultado esperado:** 200 con rol actualizado y auditoría.

#### Caso 2: Rol no permitido

- **Precondición:** Administrador.
- **Acción:** Asignar rol inexistente.
- **Resultado esperado:** 400 y sin cambios.

#### Caso 3: Usuario sin permiso

- **Precondición:** Consumidor autenticado.
- **Acción:** Acceder a un endpoint de administración.
- **Resultado esperado:** 403.

#### Caso 4: Consulta de permisos

- **Precondición:** Productor autenticado.
- **Acción:** GET /users/me/permissions.
- **Resultado esperado:** 200 con permisos de productor.

#### Caso 5: Último administrador

- **Precondición:** Solo existe un administrador.
- **Acción:** Intentar quitarle el rol.
- **Resultado esperado:** 409 y rol conservado.

### ✅ Definición de Hecho

- [ ] Roles y permisos documentados.
- [ ] Pruebas de mínimo privilegio aprobadas.
- [ ] Auditoría de asignaciones activa.
- [ ] Protección del último administrador verificada.
- [ ] Scopes y middleware alineados.

---

