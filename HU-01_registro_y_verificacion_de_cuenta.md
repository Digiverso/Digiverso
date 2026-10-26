## [HU-01] Registro y verificación de cuenta

> **Módulo:** Autenticación  
> **Submódulo(s):** SUB-01  
> **Funciones:** FUN-01, FUN-02  
> **Actor:** Visitante  
> **Prioridad:** Alta · **Puntos:** 5

### 📖 Historia de Usuario

**Dado** un visitante que desea comprar o publicar en Digiverso,  
**Para** que su cuenta quede habilitada y protegida antes de operar,  
**Que** se registre con sus datos, acepte las políticas y verifique su correo mediante un enlace temporal.

### 🎯 Beneficio esperado

El visitante accede a una cuenta confiable y la plataforma reduce cuentas falsas y correos no verificados.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-01 | Autenticación | Registro y verificación | Registrar usuario | PRC-01 |
| FUN-02 | Autenticación | Registro y verificación | Verificar cuenta | PRC-02 |

### 🔁 Flujo Esperado

- El visitante completa nombre, correo, contraseña y aceptación de políticas.
- El sistema valida formato, unicidad del correo y política de contraseña.
- Se crea la cuenta en estado pendiente y se envía un token de verificación al correo.
- El visitante abre el enlace y el sistema valida vigencia y uso único del token.
- La cuenta se activa y el visitante puede iniciar sesión.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] POST /api/v1/auth/register valida correo único, política de contraseña y aceptación de políticas.
- [ ] Un correo ya registrado responde 409 y no crea una segunda cuenta.
- [ ] La cuenta se crea en estado pendiente y no permite iniciar sesión hasta verificarse.
- [ ] POST /api/v1/auth/email/verify valida el token, su vigencia y su uso único.
- [ ] Un token expirado o reutilizado responde 410 y no activa la cuenta.
- [ ] El endpoint de registro responde sin revelar si el correo ya existía en otros flujos.

#### 2. 📆 Estructura de la información

- [ ] La respuesta de registro contiene userId, correo, estado y rol.
- [ ] La respuesta de verificación contiene cuentaId, estado y fechaVerificacion.
- [ ] Los errores usan el sobre estándar message, data y success.

```json
{
  "message": "Cuenta creada. Revisa tu correo para verificarla.",
  "data": {
    "userId": "usr_001",
    "correo": "ana@example.com",
    "estado": "pendiente_verificacion",
    "rol": "consumidor"
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- La contraseña se almacena con Argon2id o bcrypt y nunca se devuelve.
- El token de verificación se guarda hasheado y tiene vigencia AUT-03.
- El envío de correo se hace por un proveedor transaccional y se registra el intento.
- El endpoint de registro aplica rate limiting por IP y correo.

### 🚀 Endpoints

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/email/verify`

### 🧪 Requisitos de Pruebas

#### Caso 1: Registro exitoso

- **Precondición:** Correo no registrado y datos válidos.
- **Acción:** Enviar POST /auth/register.
- **Resultado esperado:** 201, cuenta pendiente y correo de verificación enviado.

#### Caso 2: Correo duplicado

- **Precondición:** El correo ya pertenece a una cuenta.
- **Acción:** Enviar el mismo correo.
- **Resultado esperado:** 409 y no se crea una cuenta nueva.

#### Caso 3: Contraseña débil

- **Precondición:** Contraseña menor a AUT-01 o sin complejidad.
- **Acción:** Enviar el registro.
- **Resultado esperado:** 400 con el detalle de la política incumplida.

#### Caso 4: Token expirado

- **Precondición:** Token con más de AUT-03 minutos.
- **Acción:** Ejecutar la verificación.
- **Resultado esperado:** 410 y la cuenta sigue pendiente.

#### Caso 5: Verificación exitosa

- **Precondición:** Token vigente y cuenta pendiente.
- **Acción:** Ejecutar la verificación.
- **Resultado esperado:** 200, cuenta activa y login habilitado.

### ✅ Definición de Hecho

- [ ] Endpoints documentados en OpenAPI.
- [ ] Pruebas de registro, duplicado, contraseña débil y token expirado aprobadas.
- [ ] Correo transaccional y plantilla de verificación verificados.
- [ ] Auditoría de registro y verificación registrada.
- [ ] Sin datos sensibles en logs.

---

