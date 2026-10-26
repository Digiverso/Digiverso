## [HU-21] Parametrización de comunidad

> **Módulo:** Comunidad  
> **Submódulo(s):** SUB-28  
> **Funciones:** FUN-64  
> **Actor:** Administrador  
> **Prioridad:** Media · **Puntos:** 3

### 📖 Historia de Usuario

**Dado** un administrador responsable de las reglas de comunidad,  
**Para** que pueda ajustar reseñas, seguimiento, feed y recomendaciones sin desplegar código,  
**Que** consulte, valide, versione y actualice los parámetros del módulo de Comunidad.

### 🎯 Beneficio esperado

La comunidad se adapta a nuevas políticas de convivencia y reputación con control y trazabilidad.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-64 | Comunidad | Parametrización de comunidad | Administrar parámetros de comunidad | PRC-64 |

### 🔁 Flujo Esperado

- El administrador consulta los parámetros vigentes.
- El sistema muestra valores, rangos y versión.
- El administrador propone cambios.
- El sistema valida rangos y dependencias.
- Se guarda una nueva versión y se audita.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] GET /api/v1/admin/community/parameters requiere rol administrador.
- [ ] PUT valida cada parámetro COMU contra tipo y rango.
- [ ] El cambio genera versión con usuario, fecha y valores anteriores.
- [ ] Un valor inválido responde 400 y no modifica la configuración.
- [ ] Los cambios se aplican a las funciones consumidoras.
- [ ] No se modifican parámetros de otros módulos.

#### 2. 📆 Estructura de la información

- [ ] La respuesta contiene versión, vigenteDesde y parámetros.
- [ ] Cada parámetro incluye código, valor, tipo y validación.
- [ ] El historial conserva versiones anteriores.

```json
{
  "message": "Parámetros de comunidad actualizados.",
  "data": {
    "version": 2,
    "vigenteDesde": "2026-10-25T18:00:00Z",
    "parametros": { "COMU-02": 1200, "COMU-05": 300 }
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- Los cambios se cachean con invalidación por versión.
- Se validan rangos y dependencias.
- El historial es inmutable.
- Solo administradores con permiso explícito escriben.

### 🚀 Endpoints

- `GET /api/v1/admin/community/parameters`
- `PUT /api/v1/admin/community/parameters`

### 🧪 Requisitos de Pruebas

#### Caso 1: Consulta

- **Precondición:** Administrador autenticado.
- **Acción:** GET /admin/community/parameters.
- **Resultado esperado:** 200 con valores y versión.

#### Caso 2: Actualización válida

- **Precondición:** Administrador.
- **Acción:** PUT con COMU-05=300.
- **Resultado esperado:** 200 y nueva versión.

#### Caso 3: Valor inválido

- **Precondición:** Administrador.
- **Acción:** PUT con COMU-01=0.
- **Resultado esperado:** 400 y sin cambios.

#### Caso 4: Acceso indebido

- **Precondición:** Consumidor autenticado.
- **Acción:** PUT /admin/community/parameters.
- **Resultado esperado:** 403.

#### Caso 5: Historial

- **Precondición:** Al menos una actualización.
- **Acción:** Consultar historial.
- **Resultado esperado:** Versiones anteriores visibles.

### ✅ Definición de Hecho

- [ ] Endpoints documentados.
- [ ] Validaciones y versionamiento probados.
- [ ] Auditoría activa.
- [ ] Cache invalidado.
- [ ] Acceso restringido.

---

