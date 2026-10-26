## [HU-13] Parametrización del catálogo

> **Módulo:** Catálogo  
> **Submódulo(s):** SUB-14  
> **Funciones:** FUN-39  
> **Actor:** Administrador  
> **Prioridad:** Media · **Puntos:** 3

### 📖 Historia de Usuario

**Dado** un administrador responsable de las reglas del catálogo,  
**Para** que pueda ajustar precios, edades, medios y sanciones sin desplegar código,  
**Que** consulte, valide, versione y actualice los parámetros del módulo de Catálogo.

### 🎯 Beneficio esperado

La operación del catálogo se adapta a nuevas políticas con trazabilidad y sin afectar otros módulos.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-39 | Catálogo | Parametrización del catálogo | Administrar parámetros del catálogo | PRC-39 |

### 🔁 Flujo Esperado

- El administrador consulta los parámetros vigentes.
- El sistema muestra valores, rangos y versión.
- El administrador propone cambios.
- El sistema valida rangos y dependencias.
- Se guarda una nueva versión y se audita.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] GET /api/v1/admin/catalog/parameters requiere rol administrador.
- [ ] PUT valida cada parámetro CAT contra tipo y rango.
- [ ] El cambio genera versión con usuario, fecha y valores anteriores.
- [ ] Un valor inválido responde 400 y no modifica la configuración.
- [ ] Los cambios se aplican a las funciones consumidoras.
- [ ] No se modifican parámetros de Autenticación, Comercio o Comunidad.

#### 2. 📆 Estructura de la información

- [ ] La respuesta contiene versión, vigenteDesde y parámetros.
- [ ] Cada parámetro incluye código, valor, tipo y validación.
- [ ] El historial conserva versiones anteriores.

```json
{
  "message": "Parámetros del catálogo actualizados.",
  "data": {
    "version": 3,
    "vigenteDesde": "2026-10-25T18:00:00Z",
    "parametros": { "CAT-01": 4000, "CAT-10": 8 }
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- Los cambios se cachean con invalidación por versión.
- Se validan dependencias como precio mínimo y moneda.
- El historial es inmutable.
- Solo administradores con permiso explícito escriben.

### 🚀 Endpoints

- `GET /api/v1/admin/catalog/parameters`
- `PUT /api/v1/admin/catalog/parameters`

### 🧪 Requisitos de Pruebas

#### Caso 1: Consulta

- **Precondición:** Administrador autenticado.
- **Acción:** GET /admin/catalog/parameters.
- **Resultado esperado:** 200 con valores y versión.

#### Caso 2: Actualización válida

- **Precondición:** Administrador.
- **Acción:** PUT con CAT-01=4000.
- **Resultado esperado:** 200 y nueva versión.

#### Caso 3: Valor inválido

- **Precondición:** Administrador.
- **Acción:** PUT con CAT-01=1000.
- **Resultado esperado:** 400 y sin cambios.

#### Caso 4: Acceso indebido

- **Precondición:** Productor autenticado.
- **Acción:** PUT /admin/catalog/parameters.
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

