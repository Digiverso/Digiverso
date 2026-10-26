## [HU-06] Parametrización de autenticación

> **Módulo:** Autenticación  
> **Submódulo(s):** SUB-07  
> **Funciones:** FUN-16  
> **Actor:** Administrador  
> **Prioridad:** Media · **Puntos:** 3

### 📖 Historia de Usuario

**Dado** un administrador responsable de la seguridad de las cuentas,  
**Para** que pueda ajustar la política de acceso sin desplegar código,  
**Que** consulte, valide, versione y actualice los parámetros del módulo de Autenticación.

### 🎯 Beneficio esperado

La organización responde a cambios de seguridad y cumple políticas internas con trazabilidad y bajo riesgo operativo.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-16 | Autenticación | Parametrización de autenticación | Administrar parámetros de autenticación | PRC-16 |

### 🔁 Flujo Esperado

- El administrador consulta los parámetros vigentes.
- El sistema muestra valores, rangos y versión actual.
- El administrador propone cambios.
- El sistema valida rangos y reglas de dependencia.
- Se guarda una nueva versión y se audita el cambio.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] GET /api/v1/admin/auth/parameters requiere rol administrador.
- [ ] PUT /api/v1/admin/auth/parameters valida cada parámetro contra su rango y tipo.
- [ ] Los cambios generan una nueva versión con usuario, fecha y valores anteriores.
- [ ] Un valor inválido responde 400 y no modifica la configuración.
- [ ] Los cambios se aplican a las funciones consumidoras en la siguiente petición.
- [ ] Un módulo no puede modificar parámetros de otro módulo.

#### 2. 📆 Estructura de la información

- [ ] La respuesta contiene versión, vigenteDesde y lista de parámetros.
- [ ] Cada parámetro incluye código, valor, tipo y validación.
- [ ] El historial permite consultar versiones anteriores.

```json
{
  "message": "Parámetros de autenticación actualizados.",
  "data": {
    "version": 4,
    "vigenteDesde": "2026-10-25T18:00:00Z",
    "parametros": {
      "AUT-01": 10,
      "AUT-06": 5,
      "AUT-07": 15
    }
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- Los parámetros se cachean con invalidación por versión.
- Los cambios quedan en un historial inmutable.
- Se validan dependencias, por ejemplo comisión y neto.
- Solo administradores con permiso explícito pueden escribir.

### 🚀 Endpoints

- `GET /api/v1/admin/auth/parameters`
- `PUT /api/v1/admin/auth/parameters`

### 🧪 Requisitos de Pruebas

#### Caso 1: Consulta de parámetros

- **Precondición:** Administrador autenticado.
- **Acción:** GET /admin/auth/parameters.
- **Resultado esperado:** 200 con valores y versión.

#### Caso 2: Actualización válida

- **Precondición:** Administrador.
- **Acción:** PUT con AUT-01=10.
- **Resultado esperado:** 200, nueva versión y auditoría.

#### Caso 3: Valor fuera de rango

- **Precondición:** Administrador.
- **Acción:** PUT con AUT-01=2.
- **Resultado esperado:** 400 y sin cambios.

#### Caso 4: Usuario no administrador

- **Precondición:** Productor autenticado.
- **Acción:** PUT /admin/auth/parameters.
- **Resultado esperado:** 403.

#### Caso 5: Historial de versiones

- **Precondición:** Al menos una actualización.
- **Acción:** Consultar historial.
- **Resultado esperado:** Versiones anteriores visibles.

### ✅ Definición de Hecho

- [ ] Endpoints de parámetros documentados.
- [ ] Validaciones y versionamiento probados.
- [ ] Auditoría de cambios activa.
- [ ] Cache invalidado por versión.
- [ ] Acceso restringido a administradores.

---

