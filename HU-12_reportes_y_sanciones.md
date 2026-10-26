## [HU-12] Reportes y sanciones

> **Módulo:** Catálogo  
> **Submódulo(s):** SUB-13  
> **Funciones:** FUN-35, FUN-36, FUN-37  
> **Actor:** Consumidor, Productor, Administrador  
> **Prioridad:** Media · **Puntos:** 5

### 📖 Historia de Usuario

**Dado** un usuario que detecta contenido que incumple las políticas,  
**Para** que la plataforma investigue y aplique una medida proporcional,  
**Que** reporte el contenido con evidencia y el administrador gestione el reporte y la sanción.

### 🎯 Beneficio esperado

La comunidad confía en un catálogo seguro y las decisiones disciplinarias quedan sustentadas.

### 🔗 Relación con la descomposición funcional

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-35 | Catálogo | Control de publicaciones | Reportar contenido | PRC-35 |
| FUN-36 | Catálogo | Control de publicaciones | Gestionar reporte | PRC-36 |
| FUN-37 | Catálogo | Control de publicaciones | Aplicar sanción | PRC-37 |

### 🔁 Flujo Esperado

- El usuario reporta un producto, reseña o usuario.
- El sistema valida motivo CAT-14 y evidencia.
- El reporte entra a la cola de control.
- El administrador evalúa antecedentes y decide desestimar o sancionar.
- Se aplica la sanción CAT-15 y se notifica a las partes.

### ✅ Criterios de Aceptación

#### 1. 🔍 Estructura y lógica del servicio

- [ ] POST /api/v1/catalog/reports exige motivo de CAT-14 y evidencia.
- [ ] No se permite más de un reporte abierto del mismo usuario sobre el mismo contenido.
- [ ] GET/PATCH /publication-control/reports permite consultar y resolver.
- [ ] La decisión puede desestimar o aplicar una sanción de CAT-15.
- [ ] Una suspensión temporal usa CAT-16 días.
- [ ] La sanción se registra con evidencia y se notifica.
- [ ] El contenido sancionado se archiva o restringe según la medida.

#### 2. 📆 Estructura de la información

- [ ] El reporte contiene id, contenidoId, motivo, evidencia, estado y fecha.
- [ ] La resolución contiene decision, sancion y observacion.
- [ ] La sanción contiene tipo, duracionDias y usuarioAfectado.

```json
{
  "message": "Reporte registrado correctamente.",
  "data": {
    "id": "rep_010",
    "contenidoId": "prod_100",
    "motivo": "derechos_autor",
    "estado": "abierto",
    "fecha": "2026-10-25T18:00:00Z"
  },
  "success": true
}
```

### 🔧 Notas Técnicas

- La evidencia se almacena con acceso restringido.
- Las sanciones son apelables por un canal definido.
- El reporte no revela la identidad del reportante.
- Las decisiones se comunican con lenguaje claro y motivo.

### 🚀 Endpoints

- `POST /api/v1/catalog/reports`
- `GET/PATCH /api/v1/catalog/publication-control/reports`
- `POST /api/v1/catalog/publication-control/sanctions`

### 🧪 Requisitos de Pruebas

#### Caso 1: Reporte válido

- **Precondición:** Usuario autenticado y motivo permitido.
- **Acción:** POST /catalog/reports.
- **Resultado esperado:** 201 con reporte abierto.

#### Caso 2: Motivo inválido

- **Precondición:** Usuario autenticado.
- **Acción:** POST con motivo desconocido.
- **Resultado esperado:** 400.

#### Caso 3: Reporte duplicado

- **Precondición:** Reporte abierto del mismo usuario y contenido.
- **Acción:** POST otro reporte.
- **Resultado esperado:** 409.

#### Caso 4: Aplicar suspensión

- **Precondición:** Reporte con evidencia y decisión.
- **Acción:** POST /sanctions.
- **Resultado esperado:** 201 con suspensión CAT-16.

#### Caso 5: Desestimar reporte

- **Precondición:** Reporte sin evidencia suficiente.
- **Acción:** PATCH /reports/{id}.
- **Resultado esperado:** 200 con decisión desestimada.

### ✅ Definición de Hecho

- [ ] Reporte, gestión y sanción documentados.
- [ ] Validación de motivos y duplicados probada.
- [ ] Evidencia protegida.
- [ ] Notificación a las partes verificada.
- [ ] Auditoría de decisiones activa.

---

