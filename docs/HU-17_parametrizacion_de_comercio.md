# [HU-17] Parametrización de comercio — implementación

**Módulo:** Comercio · **Submódulo:** SUB-21 · **Función:** FUN-53 · **Proceso:** PRC-53
**Actor:** Administrador · **Prioridad:** Media · **Puntos:** 3

### Historia de usuario

**Dado** un administrador responsable de las reglas comerciales,
**Para** que pueda ajustar comisión, pagos y liquidaciones sin desplegar código,
**Que** consulte, valide, versione y actualice los parámetros del módulo de Comercio.

**Beneficio esperado:** la plataforma adapta sus condiciones comerciales con
control y trazabilidad.

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-53 | Comercio | Parametrización de comercio | Administrar parámetros de comercio | PRC-53 |

## Endpoints

Todas las respuestas usan el sobre `{ message, data, success }`.

| Método | Ruta | Descripción | Éxito |
|---|---|---|---|
| `GET` | `/api/v1/admin/commerce/parameters` | Parámetros vigentes, versión y validaciones | 200 |
| `PUT` | `/api/v1/admin/commerce/parameters` | Validar y guardar una nueva versión | 200 |
| `GET` | `/api/v1/admin/commerce/parameters/history` | Historial de versiones (más reciente primero) | 200 |
| `GET` | `/api/v1/admin/commerce/parameters/history/{version}` | Detalle de una versión | 200 / 404 |

## Autorización

- Se reutiliza `get_actor` (Bearer de actor, cabeceras `X-Actor-Id` / `X-Actor-Roles`
  o administrador por defecto en desarrollo).
- Consulta y escritura requieren el rol `administrador` **o** el alcance explícito
  `admin.commerce.parameters.write`.
- Un alcance de otro módulo (`catalog.category.write`, `admin.catalog.parameters.write`
  o `admin.auth.parameters.write`) o el rol `productor` recibe **403**. El actor nunca
  se toma del cuerpo de la petición.

## Catálogo de parámetros

| Código | Nombre | Campo consumido | Tipo | Rango / valores | Valor inicial |
|---|---|---|---|---|---|
| `COM-01` | Comisión de la plataforma | `commerce_commission_percentage` | entero | 0 – 100 | 15 |
| `COM-02` | Neto del productor | `commerce_producer_percentage` | entero | 0 – 100 | 85 |
| `COM-03` | Moneda de ventas y liquidaciones | `commerce_currency` | texto | `COP` | `COP` |
| `COM-08` | Vigencia de la URL de descarga | `commerce_download_ttl_minutes` | entero | 1 – 1440 | 10 |
| `COM-09` | Máximo de descargas por URL | `commerce_max_downloads` | entero | 1 – 100 | 3 |
| `COM-10` | Días para la liquidación | `commerce_payout_days` | entero | 1 – 90 | 15 |
| `COM-11` | Mínimo a liquidar | `commerce_payout_minimum` | entero | 0 – 100.000.000 | 50000 |

La versión 1 se inicializa con los valores presentes en `Settings` (o con los valores
por defecto del catálogo si el campo aún no existe o está fuera de rango), por lo que
el arranque no cambia el comportamiento previo. Los códigos `COM-04` a `COM-07` no
tienen valor normativo en el repositorio, por lo que no se exponen.

### Regla de negocio

- `COM-01 + COM-02 = 100`: la comisión de la plataforma más el neto del productor
  deben cubrir exactamente el 100 % de cada venta.

La regla se valida sobre el resultado de mezclar los valores vigentes con los cambios
propuestos, de modo que no se puede eludir enviando una sola mitad. Por ejemplo,
`PUT {"parametros": {"COM-01": 10, "COM-02": 80}}` responde 400 porque la suma es 90.

## Formato de petición

```json
{
  "modulo": "comercio",
  "parametros": { "COM-01": 20, "COM-02": 80, "COM-10": 10 },
  "motivo": "Ajuste de comisión y plazos de liquidación"
}
```

- `modulo`: opcional (por defecto `comercio`). Cualquier otro valor responde 400.
- `parametros`: obligatorio y no vacío. Claves desconocidas o de otros módulos
  (`AUT-*`, `CAT-*`, `COMU-*`) responden 400.
- `motivo`: opcional; se conserva en la versión y en la auditoría.

## Formato de respuesta

Extracto (el mapa `parametros` y la lista `definiciones` contienen los siete códigos):

```json
{
  "message": "Parámetros de comercio actualizados.",
  "data": {
    "version": 2,
    "vigenteDesde": "2026-10-25T18:00:00Z",
    "modulo": "comercio",
    "parametros": { "COM-01": 15, "COM-02": 85, "COM-10": 15 },
    "definiciones": [
      {
        "codigo": "COM-01",
        "nombre": "Porcentaje de comisión de la plataforma",
        "descripcion": "Comisión de Comercio retenida sobre cada venta pagada.",
        "modulo": "comercio",
        "campo": "commerce_commission_percentage",
        "valor": 15,
        "tipo": "entero",
        "validacion": {
          "tipo": "entero", "minimo": 0, "maximo": 100,
          "requerido": true, "permitidos": []
        },
        "dependencias": [
          "COM-01 (comisión) y COM-02 (neto al productor) deben sumar 100 %."
        ]
      }
    ],
    "actualizadoPor": "usr_admin",
    "motivo": "Ajuste de comisión y plazos de liquidación"
  },
  "success": true
}
```

`parametros` mantiene el mapa código/valor del contrato; `definiciones` añade código,
valor, tipo y validación de cada parámetro. El historial expone `actorId`, `actorRoles`,
`parametros`, `anteriores`, `motivo` y `actual` por versión.

## Errores

| Situación | HTTP | `data` |
|---|---|---|
| No administrador / sin alcance | 403 | `{ "codigo": "COMMERCE_PARAMETERS_FORBIDDEN", "actorId", "roles" }` |
| Valor fuera de rango o tipo inválido | 400 | `{ "errores": [...], "versionActual" }` |
| `COM-01 + COM-02 != 100` | 400 | `{ "errores": [{ "motivo": "porcentajes", "suma", "esperado" }] }` |
| Código desconocido | 400 | `{ "codigo": "COM-99", "modulo": "comercio" }` |
| Parámetro de otro módulo | 400 | `{ "codigo", "modulo", "moduloPermitido": "comercio" }` |
| `modulo` distinto de `comercio` | 400 | `{ "modulo", "moduloPermitido" }` |
| Versión inexistente | 404 | `{ "version" }` |

**Ninguna respuesta de error escribe:** la validación ocurre antes de calcular la nueva
versión y de insertar en el historial.

## Decisiones técnicas

1. **Versionamiento inmutable.** La tabla `commerce_parameter_versions` solo admite
   `INSERT`: cada cambio guarda versión, `vigenteDesde`, actor, roles, motivo, valores
   nuevos y valores anteriores. No hay `UPDATE`/`DELETE`, por lo que el historial es
   consultable y no reescribible. La tabla se crea de forma idempotente desde el
   repositorio, sin ampliar el esquema compartido.
2. **Caché por versión.** `InMemoryCommerceParametersCache` devuelve la instantánea solo
   si el número de versión coincide. El servicio explicita `invalidate()` tras cada
   escritura. Una versión nueva nunca puede servir datos de la anterior.
3. **Consumidores en la siguiente petición.** `CommerceSettingsView` resuelve
   `value(code)` en cada acceso a un campo COM. Se encadena con
   `CatalogSettingsView` en el factory de aplicación, de modo que los servicios que
   lean `commerce_commission_percentage`, `commerce_producer_percentage`,
   `commerce_currency`, `commerce_download_ttl_minutes`, `commerce_max_downloads`,
   `commerce_payout_days` o `commerce_payout_minimum` obtienen el valor vigente sin
   reconstruir objetos y sin perder los parámetros CAT.
4. **Auditoría.** Cada actualización registra un `AuditEvent` con entidad
   `parametros_comercio`, entidad `commerce:version-N`, acción
   `parametros_actualizados`, actor y el diff de valores (anteriores vs. nuevos).
5. **Aislamiento por módulo.** Comercio está etiquetado con `modulo=comercio`; los
   prefijos `AUT-`, `CAT-` y `COMU-` se rechazan explícitamente y el campo `modulo`
   debe coincidir. Los alcances de autenticación, catálogo o comunidad tampoco
   autorizan la escritura.

## Criterios de aceptación cubiertos

- [x] `GET` y `PUT` requieren rol administrador o alcance explícito.
- [x] `PUT` valida tipo y rango de cada parámetro COM.
- [x] `COM-01` y `COM-02` deben sumar 100 %.
- [x] Cada cambio genera versión con usuario, fecha y valores anteriores.
- [x] Un valor inválido responde 400 y no modifica la configuración.
- [x] No se modifican parámetros de otros módulos.
- [x] La respuesta contiene versión, `vigenteDesde` y parámetros; cada parámetro
      incluye código, valor, tipo y validación; el historial conserva versiones previas.

## Pruebas

```bash
pytest -q tests/test_commerce_parameters_api.py
pytest -q
```

La suite cubre los cinco casos de aceptación (consulta, actualización válida,
porcentajes inconsistentes, acceso indebido e historial), además de tipos, rangos,
alcance explícito, aislamiento de módulos, códigos desconocidos, invalidación de
caché y encadenamiento de la vista de `Settings`.
