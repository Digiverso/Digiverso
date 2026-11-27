# [HU-13] Parametrización del catálogo — implementación

**Módulo:** Catálogo · **Submódulo:** SUB-14 · **Función:** FUN-39 · **Proceso:** PRC-39
**Actor:** Administrador · **Prioridad:** Media · **Puntos:** 3

### Historia de usuario

**Dado** un administrador responsable de las reglas del catálogo,
**Para** que pueda ajustar precios, edades, medios y sanciones sin desplegar código,
**Que** consulte, valide, versione y actualice los parámetros del módulo de Catálogo.

**Beneficio esperado:** la operación del catálogo se adapta a nuevas políticas con
trazabilidad y sin afectar otros módulos.

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-39 | Catálogo | Parametrización del catálogo | Administrar parámetros del catálogo | PRC-39 |

## Endpoints

Todas las respuestas usan el sobre `{ message, data, success }`.

| Método | Ruta | Descripción | Éxito |
|---|---|---|---|
| `GET` | `/api/v1/admin/catalog/parameters` | Parámetros vigentes, versión y validaciones | 200 |
| `PUT` | `/api/v1/admin/catalog/parameters` | Validar y guardar una nueva versión | 200 |
| `GET` | `/api/v1/admin/catalog/parameters/history` | Historial de versiones (más reciente primero) | 200 |
| `GET` | `/api/v1/admin/catalog/parameters/history/{version}` | Detalle de una versión | 200 / 404 |

## Autorización

- Se reutiliza `get_actor` (Bearer de actor, cabeceras `X-Actor-Id` / `X-Actor-Roles`
  o administrador por defecto en desarrollo).
- Consulta y escritura requieren el rol `administrador` **o** el alcance explícito
  `admin.catalog.parameters.write`.
- Un alcance de otro módulo (`catalog.category.write`, `admin.auth.parameters.write`)
  o el rol `productor` recibe **403**. El actor nunca se toma del cuerpo de la petición.

## Catálogo de parámetros

| Código | Nombre | Campo consumido | Tipo | Rango / valores | Valor inicial |
|---|---|---|---|---|---|
| `CAT-01` | Precio mínimo del producto | `product_min_price` | entero | 3500 – 1.000.000 | 3500 |
| `CAT-02` | Moneda del catálogo | `product_currency` | texto | `COP` | `COP` |
| `CAT-03` | Edad máxima | `product_max_age` | entero | 1 – 120 | 99 |
| `CAT-05` | Formatos de imagen | `media_image_formats` | lista | `jpg`, `jpeg`, `png`, `webp` | `jpg`, `png`, `webp` |
| `CAT-06` | Tamaño máximo de imagen | `media_max_image_bytes` | entero | 1 KiB – 100 MiB | 10 MiB |
| `CAT-07` | Formatos de video | `media_video_formats` | lista | `mp4`, `m4v`, `mov`, `webm` | `mp4`, `mov`, `webm` |
| `CAT-08` | Tamaño máximo de video | `media_max_video_bytes` | entero | 1 KiB – 500 MiB | 200 MiB |
| `CAT-09` | Mínimo de imágenes | `product_min_images` | entero | 0 – 10 | 1 |
| `CAT-10` | Máximo de medios por producto | `media_max_per_product` | entero | 1 – 50 | 10 |
| `CAT-11` | Longitud máxima del nombre | `product_name_max_length` | entero | 2 – 200 | 120 |
| `CAT-12` | Longitud máxima de la descripción | `product_description_max_length` | entero | 1 – 10.000 | 2000 |
| `CAT-13` | Máximo de categorías por producto | `product_max_categories` | entero | 1 – 20 | 5 |
| `CAT-16` | Días de suspensión por sanción | `report_suspension_days` | entero | 1 – 90 | 7 |
| `CAT-17` | Longitud máxima del nombre de categoría | `category_name_max_length` | entero | 2 – 120 | 80 |

La versión 1 se inicializa con los valores presentes en `Settings` (o con los valores
por defecto del catálogo si el campo aún no existe o está fuera de rango), por lo que
el arranque no cambia el comportamiento previo. `CAT-16` y `CAT-17` se declaran desde
ya para que la parametrización sea compatible con HU-11/HU-12 cuando se fusionen;
`CAT-14` y `CAT-15` son políticas enumeradas de reportes/sanciones, no valores
configurables, por lo que no se exponen aquí.

### Dependencias

- `CAT-02 == COP`: el precio mínimo `CAT-01` solo se admite en la moneda del catálogo.
- `CAT-05` y `CAT-07` no pueden compartir formatos (un formato no es imagen y video a la vez).
- `CAT-06 <= CAT-08`: una imagen no puede pesar más que un video.
- `CAT-09 <= CAT-10`: el mínimo de imágenes no puede superar el máximo de medios.

Las dependencias se validan sobre el resultado de mezclar los valores vigentes con los
cambios propuestos, de modo que no se pueden eludir enviando una sola mitad de la regla.

## Formato de petición

```json
{
  "modulo": "catalogo",
  "parametros": { "CAT-01": 4000, "CAT-10": 8 },
  "motivo": "Ajuste de política de precios y medios"
}
```

- `modulo`: opcional (por defecto `catalogo`). Cualquier otro valor responde 400.
- `parametros`: obligatorio y no vacío. Claves desconocidas o de otros módulos
  (`AUT-*`, `COM-*`, `COMU-*`) responden 400.
- `motivo`: opcional; se conserva en la versión y en la auditoría.

## Formato de respuesta

```json
{
  "message": "Parámetros del catálogo actualizados.",
  "data": {
    "version": 3,
    "vigenteDesde": "2026-10-25T18:00:00Z",
    "modulo": "catalogo",
    "parametros": { "CAT-01": 4000, "CAT-10": 8 },
    "definiciones": [
      {
        "codigo": "CAT-01",
        "nombre": "Precio mínimo del producto",
        "descripcion": "Precio mínimo en COP exigido al crear o editar productos.",
        "modulo": "catalogo",
        "campo": "product_min_price",
        "valor": 4000,
        "tipo": "entero",
        "validacion": {
          "tipo": "entero", "minimo": 3500, "maximo": 1000000,
          "requerido": true, "permitidos": [], "maxItems": null
        },
        "dependencias": ["CAT-01 (precio mínimo) solo se admite con CAT-02 = COP."]
      }
    ],
    "actualizadoPor": "usr_admin",
    "motivo": "Ajuste de política de precios y medios"
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
| No administrador / sin alcance | 403 | `{ "codigo": "CATALOG_PARAMETERS_FORBIDDEN", "actorId", "roles" }` |
| Valor fuera de rango o tipo inválido | 400 | `{ "errores": [...], "versionActual" }` |
| Dependencia incumplida | 400 | `{ "errores": [{ "motivo": "dependencia", "mensaje" }] }` |
| Código desconocido | 400 | `{ "codigo": "CAT-99", "modulo": "catalogo" }` |
| Parámetro de otro módulo | 400 | `{ "codigo", "modulo", "moduloPermitido": "catalogo" }` |
| `modulo` distinto de `catalogo` | 400 | `{ "modulo", "moduloPermitido" }` |
| Versión inexistente | 404 | `{ "version" }` |

**Ninguna respuesta de error escribe:** la validación ocurre antes de calcular la nueva
versión y de insertar en el historial.

## Decisiones técnicas

1. **Versionamiento inmutable.** La tabla `catalog_parameter_versions` solo admite
   `INSERT`: cada cambio guarda versión, `vigenteDesde`, actor, roles, motivo, valores
   nuevos y valores anteriores. No hay `UPDATE`/`DELETE`, por lo que el historial es
   consultable y no reescribible. La tabla se crea de forma idempotente desde el
   repositorio, sin ampliar el esquema compartido.
2. **Caché por versión.** `InMemoryCatalogParametersCache` devuelve la instantánea solo
   si el número de versión coincide. El servicio explicita `invalidate()` tras cada
   escritura. Una versión nueva nunca puede servir datos de la anterior.
3. **Consumidores en la siguiente petición.** `CatalogSettingsView` resuelve
   `value(code)` en cada acceso a un campo CAT. Se inyecta en `CategoryService`,
   `ProductService` y `MediaService` desde el factory de aplicación, por lo que
   precios, edades, longitudes, categorías y reglas de medios se reevalúan sin
   reconstruir servicios. Las listas se convierten a tupla cuando el campo lo exige.
4. **Auditoría.** Cada actualización registra un `AuditEvent` con entidad
   `parametros_catalogo`, entidad `catalog:version-N`, acción
   `parametros_actualizados`, actor y el diff de valores (anteriores vs. nuevos).
5. **Aislamiento por módulo.** El catálogo está etiquetado con `modulo=catalogo`; los
   prefijos `AUT-`, `COM-` y `COMU-` se rechazan explícitamente y el campo `modulo`
   debe coincidir. Los alcances de autenticación o de categorías tampoco autorizan
   la escritura.

## Criterios de aceptación cubiertos

- [x] `GET` y `PUT` requieren rol administrador o alcance explícito.
- [x] `PUT` valida tipo, rango y dependencias antes de escribir.
- [x] Cada cambio genera versión con usuario, fecha y valores anteriores.
- [x] Un valor inválido responde 400 y no modifica la configuración.
- [x] Los cambios se aplican a las funciones consumidoras.
- [x] No se modifican parámetros de Autenticación, Comercio ni Comunidad.
- [x] La respuesta contiene versión, `vigenteDesde` y parámetros; cada parámetro
      incluye código, valor, tipo y validación; el historial conserva versiones previas.

## Pruebas

```bash
pytest -q tests/test_catalog_parameters_api.py
pytest -q
```

La suite cubre los cinco casos de aceptación (consulta, actualización válida, valor
inválido, acceso indebido e historial), además de dependencias, tipos, alcance
explícito, aislamiento de módulos, desconocimiento de códigos, invalidación de caché
y efecto real en la creación de productos. La suite completa pasa con 174 pruebas.
