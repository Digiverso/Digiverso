## [HU-02] Sesión y recuperación de contraseña

> **Módulo:** Autenticación  
> **Submódulo(s):** SUB-02, SUB-03  
> **Funciones:** FUN-03, FUN-04, FUN-05, FUN-06  
> **Actor:** Consumidor, Productor, Administrador  
> **Prioridad:** Alta · **Puntos:** 5

### 📖 Historia de Usuario

**Dado** un usuario registrado y verificado,  
**Para** que mantenga una sesión segura y pueda recuperar el acceso si olvida su contraseña,  
**Que** inicie y cierre sesión, solicite un enlace de recuperación y restablezca su contraseña.

### 🎯 Beneficio esperado

El usuario conserva el acceso sin fricción y la plataforma reduce el riesgo de sesiones y contraseñas comprometidas.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-03 | Autenticación | Sesión | Iniciar sesión | PRC-03 |
| FUN-04 | Autenticación | Sesión | Cerrar sesión | PRC-04 |
| FUN-05 | Autenticación | Recuperación de acceso | Solicitar recuperación de contraseña | PRC-05 |
| FUN-06 | Autenticación | Recuperación de acceso | Restablecer contraseña | PRC-06 |

### 🔁 Flujo Esperado

- El usuario envía correo y contraseña al inicio de sesión.
- El sistema valida credenciales, estado de cuenta y bloqueo por intentos fallidos.
- Se emiten access token y refresh token con vigencias AUT-04 y AUT-05.
- El usuario puede cerrar sesión y revocar el refresh token.
- Si olvida la contraseña, solicita un enlace temporal y define una nueva con la política vigente.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] POST /api/v1/auth/login valida credenciales y cuenta verificada.
- [ ] Tras AUT-06 intentos fallidos la cuenta se bloquea AUT-07 minutos.
- [ ] El access token vence en AUT-04 minutos y el refresh token en AUT-05 días.
- [ ] POST /api/v1/auth/logout revoca la sesión y el refresh token.
- [ ] POST /api/v1/auth/password/forgot responde de forma genérica exista o no el correo.
- [ ] POST /api/v1/auth/password/reset valida token, vigencia AUT-08 y política de contraseña.
- [ ] Al restablecer la contraseña se revocan las sesiones activas.

#### 2. 📆 Estructura de la información

- [ ] La respuesta de login contiene accessToken, refreshToken y expiraEn.
- [ ] La respuesta de recuperación no revela si el correo existe.
- [ ] El restablecimiento devuelve un mensaje de confirmación sin datos sensibles.

```json
{
  "message": "Inicio de sesión exitoso.",
  "data": {
    "accessToken": "eyJ...",
    "refreshToken": "rt_...",
    "expiraEn": 900,
    "usuario": { "id": "usr_001", "rol": "consumidor" }
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- Los tokens se firman con RS256 y se validan en el API Gateway.
- El refresh token se rota y se almacena con hash.
- El enlace de recuperación es de un solo uso y no se registra en logs.
- Se aplica rate limiting a login y recuperación.

### 🚀 Endpoints

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/password/forgot`
- `POST /api/v1/auth/password/reset`

### 🧪 Requisitos de Pruebas

#### Caso 1: Login exitoso

- **Precondición:** Cuenta verificada y credenciales correctas.
- **Acción:** POST /auth/login.
- **Resultado esperado:** 200 con tokens y expiración.

#### Caso 2: Bloqueo por intentos

- **Precondición:** Cuenta activa con AUT-06 intentos fallidos.
- **Acción:** Intentar un login más.
- **Resultado esperado:** 423 o 429 con bloqueo temporal.

#### Caso 3: Cierre de sesión

- **Precondición:** Sesión activa.
- **Acción:** POST /auth/logout con refresh token.
- **Resultado esperado:** 204 y token revocado.

#### Caso 4: Correo inexistente

- **Precondición:** Correo no registrado.
- **Acción:** POST /auth/password/forgot.
- **Resultado esperado:** 200 con mensaje genérico.

#### Caso 5: Token de recuperación expirado

- **Precondición:** Token con más de AUT-08 minutos.
- **Acción:** POST /auth/password/reset.
- **Resultado esperado:** 410 y contraseña sin cambios.

### ✅ Definición de Hecho

- [ ] Login, logout y recuperación documentados.
- [ ] Pruebas de bloqueo, expiración y revocación aprobadas.
- [ ] Tokens y enlaces no se escriben en logs.
- [ ] Plantilla de recuperación verificada.
- [ ] Auditoría de accesos y cambios de contraseña.

---

