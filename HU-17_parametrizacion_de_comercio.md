## [HU-17] Parametrización de comercio

> **Módulo:** Comercio  
> **Submódulo(s):** SUB-21  
> **Funciones:** FUN-53  
> **Actor:** Administrador  
> **Prioridad:** Media · **Puntos:** 3

### 📖 Historia de Usuario

**Dado** un administrador responsable de las reglas comerciales,  
**Para** que pueda ajustar comisión, pagos y liquidaciones sin desplegar código,  
**Que** consulte, valide, versione y actualice los parámetros del módulo de Comercio.

### 🎯 Beneficio esperado

La plataforma adapta sus condiciones comerciales con control y trazabilidad.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-53 | Comercio | Parametrización de comercio | Administrar parámetros de comercio | PRC-53 |

### 🔁 Flujo Esperado

- El administrador consulta los parámetros vigentes.
- El sistema muestra valores, rangos y versión.
- El administrador propone cambios.
- El sistema valida rangos y que comisión más neto sumen 100 %.
- Se guarda una nueva versión y se audita.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] GET /api/v1/admin/commerce/parameters requiere rol administrador.
- [ ] PUT valida cada parámetro COM contra tipo y rango.
- [ ] COM-01 y COM-02 deben sumar 100 %.
- [ ] El cambio genera versión con usuario, fecha y valores anteriores.
- [ ] Un valor inválido responde 400 y no modifica la configuración.
- [ ] No se modifican parámetros de otros módulos.

#### 2. 📆 Estructura de la información

- [ ] La respuesta contiene versión, vigenteDesde y parámetros.
- [ ] Cada parámetro incluye código, valor, tipo y validación.
- [ ] El historial conserva versiones anteriores.

```json
{
  "message": "Parámetros de comercio actualizados.",
  "data": {
    "version": 2,
    "vigenteDesde": "2026-10-25T18:00:00Z",
    "parametros": { "COM-01": 15, "COM-02": 85, "COM-10": 15 }
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- Los cambios se cachean con invalidación por versión.
- Se valida la suma de porcentajes.
- El historial es inmutable.
- Solo administradores con permiso explícito escriben.

### 🚀 Endpoints

- `GET /api/v1/admin/commerce/parameters`
- `PUT /api/v1/admin/commerce/parameters`

### 🧪 Requisitos de Pruebas

#### Caso 1: Consulta

- **Precondición:** Administrador autenticado.
- **Acción:** GET /admin/commerce/parameters.
- **Resultado esperado:** 200 con valores y versión.

#### Caso 2: Actualización válida

- **Precondición:** Administrador.
- **Acción:** PUT con COM-10=15.
- **Resultado esperado:** 200 y nueva versión.

#### Caso 3: Porcentajes inconsistentes

- **Precondición:** Administrador.
- **Acción:** PUT con COM-01=10 y COM-02=80.
- **Resultado esperado:** 400 y sin cambios.

#### Caso 4: Acceso indebido

- **Precondición:** Productor autenticado.
- **Acción:** PUT /admin/commerce/parameters.
- **Resultado esperado:** 403.

#### Caso 5: Historial

- **Precondición:** Al menos una actualización.
- **Acción:** Consultar historial.
- **Resultado esperado:** Versiones anteriores visibles.

### ✅ Definición de Hecho

- [ ] Endpoints documentados.
- [ ] Validaciones y versionamiento probados.
- [ ] Suma de porcentajes verificada.
- [ ] Auditoría activa.
- [ ] Acceso restringido.

---

