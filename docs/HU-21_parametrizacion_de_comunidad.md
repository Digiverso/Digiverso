# [HU-21] Parametrización de comunidad — implementación

**Módulo:** Comunidad · **Submódulo:** SUB-28 · **Función:** FUN-64 · **Proceso:** PRC-64
**Actor:** Administrador · **Prioridad:** Media · **Puntos:** 3

### Historia de usuario

**Dado** un administrador responsable de las reglas de comunidad,
**Para** que pueda ajustar reseñas, seguimiento, feed y recomendaciones sin desplegar código,
**Que** consulte, valide, versione y actualice los parámetros del módulo de Comunidad.

**Beneficio esperado:** la comunidad se adapta a nuevas políticas de convivencia y
reputación con control y trazabilidad.

| FUN | Módulo | Submódulo | Funcionalidad | Proceso |
|---|---|---|---|---|
| FUN-64 | Comunidad | Parametrización de comunidad | Administrar parámetros de comunidad | PRC-64 |

## Endpoints

Todas las respuestas usan el sobre `{ message, data, success }`.

| Método | Ruta | Descripción | Éxito |
|---|---|---|---|
| `GET` | `/api/v1/admin/community/parameters` | Parámetros vigentes, versión y validaciones | 200 |
| `PUT` | `/api/v1/admin/community/parameters` | Validar y guardar una nueva versión | 200 |
| `GET` | `/api/v1/admin/community/parameters/history` | Historial de versiones (más reciente primero) | 200 |
| `GET` | `/api/v1/admin/community/parameters/history/{version}` | Detalle de una versión | 200 / 404 |

## Autorización

- Se reutiliza `get_actor` (Bearer de actor, cabeceras `X-Actor-Id` / `X-Actor-Roles`
  o administrador por defecto en desarrollo).
- Consulta y escritura requieren el rol `administrador` **o** el alcance explícito
  `admin.community.parameters.write`.
- El rol `consumidor` o un alcance de otro módulo recibe **403**. El actor nunca se
  toma del cuerpo de la petición.

## Catálogo de parámetros

| Código | Nombre | Campo consumido | Tipo | Rango / valores | Valor inicial |
|---|---|---|---|---|---|
| `COMU-01` | Calificación mínima de una reseña | `community_rating_min` | entero | 1 – 5 | 1 |
| `COMU-02` | Longitud máxima del texto de una reseña | `community_text_max_length` | entero | 100 – 2000 | 1000 |
| `COMU-03` | Una reseña por usuario y producto | `community_unique_review` | booleano | `true` / `false` | `true` |
| `COMU-04` | Reseñas solo con compra acreditada | `community_require_purchase` | booleano | `true` / `false` | `true` |
| `COMU-05` | Máximo de usuarios seguidos | `community_max_following` | entero | 1 – 1000 | 200 |
| `COMU-07` | Tamaño máximo de página del feed | `community_max_page_size` | entero | 1 – 500 (con dependencia) | 100 |
| `COMU-08` | Máximo de categorías de interés | `community_max_interests` | entero | 1 – 50 | 10 |
| `COMU-09` | Máximo de recomendaciones | `community_max_recommendations` | entero | 1 – 100 | 20 |
| `COMU-10` | Ventana de novedad de las recomendaciones | `community_recent_days` | entero | 1 – 365 | 30 |
| `COMU-11` | Notificaciones de comunidad activas | `community_notifications_enabled` | booleano | `true` / `false` | `true` |

Los rangos y valores por defecto son los declarados por las historias de comunidad
presentes en el repositorio (HU-18, HU-19 y HU-20). `COMU-06` no aparece en la
descomposición funcional disponible, por lo que no se expone como parámetro
configurable. La versión 1 se inicializa con los valores de `Settings` (o con los
valores por defecto si el campo aún no existe), de modo que el arranque no cambia
el comportamiento previo.

### Dependencias

- `COMU-07 >= 20`: el tamaño máximo de página no puede ser menor que el tamaño
  por defecto (20) usado por feed y recomendaciones.

Las dependencias se validan sobre el resultado de mezclar los valores vigentes con
los cambios propuestos, de modo que no se pueden eludir enviando una sola mitad.

## Formato de petición

```json
{
  "modulo": "comunidad",
  "parametros": { "COMU-02": 1200, "COMU-05": 300 },
  "motivo": "Nueva política de convivencia"
}
```

- `modulo`: opcional (por defecto `comunidad`). Cualquier otro valor responde 400.
- `parametros`: obligatorio y no vacío. Claves desconocidas o de otros módulos
  (`AUT-*`, `CAT-*`, `COM-*`) responden 400.
- `motivo`: opcional; se conserva en la versión y en la auditoría.

## Formato de respuesta

```json
{
  "message": "Parámetros de comunidad actualizados.",
  "data": {
    "version": 2,
    "vigenteDesde": "2026-10-25T18:00:00Z",
    "modulo": "comunidad",
    "parametros": { "COMU-02": 1200, "COMU-05": 300 },
    "definiciones": [
      {
        "codigo": "COMU-05",
        "nombre": "Máximo de usuarios seguidos",
        "descripcion": "Cantidad máxima de usuarios que un miembro puede seguir.",
        "modulo": "comunidad",
        "campo": "community_max_following",
        "valor": 300,
        "tipo": "entero",
        "validacion": {
          "tipo": "entero", "minimo": 1, "maximo": 1000, "requerido": true
        },
        "dependencias": []
      }
    ],
    "actualizadoPor": "usr_admin",
    "motivo": "Nueva política de convivencia"
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
| No administrador / sin alcance | 403 | `{ "codigo": "COMMUNITY_PARAMETERS_FORBIDDEN", "actorId", "roles" }` |
| Valor fuera de rango o tipo inválido | 400 | `{ "errores": [...], "versionActual" }` |
| Dependencia incumplida | 400 | `{ "errores": [{ "motivo": "dependencia", "mensaje" }] }` |
| Código desconocido | 400 | `{ "codigo": "COMU-99", "modulo": "comunidad" }` |
| Parámetro de otro módulo | 400 | `{ "codigo", "modulo", "moduloPermitido": "comunidad" }` |
| `modulo` distinto de `comunidad` | 400 | `{ "modulo", "moduloPermitido" }` |
| Versión inexistente | 404 | `{ "version" }` |

**Ninguna respuesta de error escribe:** la validación ocurre antes de calcular la nueva
versión y de insertar en el historial.

## Decisiones técnicas

1. **Archivos nuevos.** Dominio, errores, repositorio, caché, esquemas, servicio y
   router son propios de HU-21; no se amplían los módulos compartidos tocados por
   otras historias. En `app/main.py` solo se añaden importaciones, la construcción
   del servicio, el registro del router, una etiqueta OpenAPI y la ruta de validación.
2. **Versionamiento inmutable.** La tabla `community_parameter_versions` solo admite
   `INSERT`: guarda versión, `vigenteDesde`, actor, roles, motivo, valores nuevos y
   anteriores. Se crea de forma idempotente desde el repositorio.
3. **Caché por versión.** `InMemoryCommunityParametersCache` solo sirve la instantánea
   cuando coincide el número de versión; se invalida explícitamente tras cada escritura.
   Si las ramas HU-18/HU-19 están fusionadas, también se limpian `rating_cache` y
   `community_feed_cache`.
4. **Consumidores.** `CommunitySettingsView` devuelve el valor vigente en cada acceso
   y expone los nombres usados por `CommunitySettings`. Al actualizar, el servicio
   propaga los cambios a los objetos de configuración registrados (sin cambiar su
   tipo, para mantener `dataclasses.replace`), de modo que reseñas, seguimiento,
   feed, recomendaciones y notificaciones lean la nueva versión en la siguiente
   operación. El enlace es opcional: funciona con o sin esas ramas presentes.
5. **Auditoría.** Cada cambio registra un `AuditEvent` con entidad
   `parametros_comunidad`, entidad `community:version-N`, acción
   `parametros_actualizados`, actor y el diff de valores.
6. **Aislamiento por módulo.** Prefijos `AUT-`, `CAT-` y `COM-` se rechazan; el campo
   `modulo` debe ser `comunidad`. Los alcances de autenticación o catálogo no autorizan
   la escritura.

## Criterios de aceptación cubiertos

- [x] `GET` y `PUT` requieren rol administrador o alcance explícito.
- [x] `PUT` valida tipo, rango y dependencias antes de escribir.
- [x] Cada cambio genera versión con usuario, fecha y valores anteriores.
- [x] Un valor inválido responde 400 y no modifica la configuración.
- [x] Los cambios se aplican a las funciones consumidoras.
- [x] No se modifican parámetros de otros módulos.
- [x] La respuesta contiene versión, `vigenteDesde` y parámetros; cada parámetro
      incluye código, valor, tipo y validación; el historial conserva versiones previas.

## Pruebas

```bash
pytest -q tests/test_community_parameters_api.py
pytest -q
```
