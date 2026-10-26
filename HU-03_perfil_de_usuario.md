## [HU-03] Perfil de usuario

> **Módulo:** Autenticación  
> **Submódulo(s):** SUB-04  
> **Funciones:** FUN-07, FUN-08  
> **Actor:** Consumidor, Productor  
> **Prioridad:** Media · **Puntos:** 3

### 📖 Historia de Usuario

**Dado** un usuario autenticado,  
**Para** que sus datos personales y su imagen estén actualizados,  
**Que** consulte y edite su perfil sin poder modificar rol, correo verificado ni datos de otros usuarios.

### 🎯 Beneficio esperado

El usuario controla su identidad digital y la plataforma conserva datos consistentes para compras y notificaciones.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-07 | Autenticación | Perfil | Consultar perfil | PRC-07 |
| FUN-08 | Autenticación | Perfil | Editar perfil | PRC-08 |

### 🔁 Flujo Esperado

- El usuario abre su perfil.
- El sistema devuelve datos públicos y privados permitidos.
- El usuario edita nombre, biografía o foto.
- El sistema valida campos y tamaño de imagen AUT-12.
- Se guarda el cambio y se registra en auditoría.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] GET /api/v1/users/me devuelve solo el perfil del usuario autenticado.
- [ ] PATCH /api/v1/users/me acepta nombre, biografía y foto; rechaza rol, correo y estado.
- [ ] La foto respeta el tamaño máximo AUT-12 y formatos de imagen permitidos.
- [ ] Un usuario no puede consultar ni editar el perfil de otro.
- [ ] Los cambios quedan auditados con usuario, fecha y campos modificados.

#### 2. 📆 Estructura de la información

- [ ] El perfil contiene id, nombre, correo, rol, biografía, foto y fechaRegistro.
- [ ] La respuesta de edición devuelve el perfil actualizado.
- [ ] Los errores de validación indican el campo afectado.

```json
{
  "message": "Perfil actualizado correctamente.",
  "data": {
    "id": "usr_001",
    "nombre": "Ana Torres",
    "correo": "ana@example.com",
    "rol": "productor",
    "biografia": "Ilustradora digital.",
    "foto": "https://cdn.digiverso.com/users/usr_001.jpg"
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- El correo se cambia por un flujo separado con verificación.
- La foto se almacena en S3 y se sirve por CDN.
- Se aplica validación de tipo real de archivo, no solo extensión.
- Los campos sensibles se excluyen de la respuesta.

### 🚀 Endpoints

- `GET /api/v1/users/me`
- `PATCH /api/v1/users/me`

### 🧪 Requisitos de Pruebas

#### Caso 1: Consulta de perfil

- **Precondición:** Usuario autenticado.
- **Acción:** GET /users/me.
- **Resultado esperado:** 200 con el perfil propio.

#### Caso 2: Edición válida

- **Precondición:** Usuario autenticado.
- **Acción:** PATCH con nombre y biografía.
- **Resultado esperado:** 200 con datos actualizados y auditoría.

#### Caso 3: Foto demasiado grande

- **Precondición:** Archivo mayor a AUT-12.
- **Acción:** PATCH con la foto.
- **Resultado esperado:** 400 y sin cambios.

#### Caso 4: Intento de cambiar rol

- **Precondición:** Usuario autenticado.
- **Acción:** PATCH con rol=admin.
- **Resultado esperado:** 400 o 403 y rol sin cambios.

#### Caso 5: Perfil ajeno

- **Precondición:** Usuario autenticado.
- **Acción:** Solicitar otro userId.
- **Resultado esperado:** 403 o 404.

### ✅ Definición de Hecho

- [ ] Endpoints de perfil documentados.
- [ ] Validación de foto y campos probada.
- [ ] Auditoría de cambios activa.
- [ ] Datos sensibles excluidos.
- [ ] Pruebas de acceso a perfiles ajenos aprobadas.

---

