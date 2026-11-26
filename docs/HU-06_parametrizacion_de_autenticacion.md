# HU-06 · Parametrización de autenticación

**Módulo:** Autenticación · **Submódulo:** SUB-07 · **Función:** FUN-16 · **Proceso:** PRC-16
**Prioridad:** Media · **Puntos:** 3 · **Actor:** Administrador

## Objetivo

Permitir al administrador consultar, validar, versionar y actualizar los parámetros del
módulo de Autenticación sin desplegar código, con trazabilidad y bajo riesgo operativo.

## Endpoints

| Método | Ruta | Descripción | Éxito |
|---|---|---|---|
| `GET` | `/api/v1/admin/auth/parameters` | Parámetros vigentes, versión y metadatos | 200 |
| `PUT` | `/api/v1/admin/auth/parameters` | Validar y guardar una nueva versión | 200 |
| `GET` | `/api/v1/admin/auth/parameters/history` | Historial de versiones (más reciente primero) | 200 |
| `GET` | `/api/v1/admin/auth/parameters/history/{version}` | Detalle de una versión | 200 / 404 |

Todas las operaciones existen bajo `GET`/`PUT`; el historial solo consume `GET`.

## Autorización

- Se reutiliza `get_actor` (Bearer de actor, cabeceras `X-Actor-Id` / `X-Actor-Roles` o
  administrador por defecto en desarrollo).
- Consulta y escritura requieren el rol `administrador` **o** el alcance explícito
  `admin.auth.parameters.write`.
- Un alcance de otro módulo (`catalog.category.write`, `catalog.product.write`) o el rol
  `productor` recibe **403**. Así un módulo no puede administrar parámetros ajenos.
- El actor nunca se toma del cuerpo de la petición.

## Catálogo de parámetros

| Código | Nombre | Campo consumido | Tipo | Rango | Valor inicial |
|---|---|---|---|---|---|
| `AUT-01` | Intentos fallidos máximos | `max_failed_login_attempts` | entero | 3 – 10 | 5 |
| `AUT-02` | Longitud mínima de contraseña | `password_min_length` | entero | 8 – 64 | 8 |
| `AUT-03` | Vigencia del token de acceso (min) | `access_token_ttl_minutes` | entero | 5 – 1440 | 15 |
| `AUT-04` | Vigencia del token de refresco (días) | `refresh_token_ttl_days` | entero | 1 – 90 | 7 |
| `AUT-05` | Vigencia del token de verificación (min) | `verification_token_ttl_minutes` | entero | 5 – 1440 | 15 |
| `AUT-06` | Duración del bloqueo (min) | `account_lock_minutes` | entero | 5 – 60 | 15 |
| `AUT-07` | Vigencia del token de recuperación (min) | `password_reset_ttl_minutes` | entero | 5 – 1440 | 30 |

La versión 1 se inicializa con los valores presentes en `Settings` (o con los valores
por defecto del catálogo si alguno estuviera fuera de rango), por lo que el arranque no
cambia el comportamiento previo.

### Dependencias

- `AUT-03 <= AUT-04 × 1440`: la vigencia del access token no puede superar la del refresh
  token expresada en minutos.
- `AUT-05 <= AUT-07`: el enlace de verificación no puede durar más que el de recuperación.

Las dependencias se validan sobre el resultado de mezclar los valores vigentes con los
cambios propuestos, de modo que no se pueden eludir enviando una sola mitad de la regla.

## Formato de petición

```json
{
  "modulo": "autenticacion",
  "parametros": { "AUT-01": 10, "AUT-06": 5, "AUT-07": 15 },
  "motivo": "Ajuste de política de bloqueos"
}
```

- `modulo`: opcional (por defecto `autenticacion`). Cualquier otro valor responde 400.
- `parametros`: obligatorio y no vacío. Claves desconocidas o de otros módulos
  (`CAT-*`, `PROD-*`) responden 400.
- `motivo`: opcional; se conserva en la versión y en la auditoría.

## Formato de respuesta

```json
{
  "message": "Parámetros de autenticación actualizados.",
  "data": {
    "version": 4,
    "vigenteDesde": "2026-10-25T18:00:00Z",
    "modulo": "autenticacion",
    "parametros": { "AUT-01": 10, "AUT-06": 5, "AUT-07": 15 },
    "definiciones": [
      {
        "codigo": "AUT-01",
        "nombre": "Intentos fallidos máximos",
        "descripcion": "Intentos de inicio de sesión fallidos antes de bloquear la cuenta.",
        "modulo": "autenticacion",
        "valor": 10,
        "tipo": "entero",
        "validacion": { "tipo": "entero", "minimo": 3, "maximo": 10, "requerido": true },
        "dependencias": []
      }
    ],
    "actualizadoPor": "usr_admin",
    "motivo": "Ajuste de política de bloqueos"
  },
  "success": true
}
```

`parametros` mantiene el mapa código/valor del contrato; `definiciones` añade código,
valor, tipo y validación de cada parámetro.

## Errores

| Situación | HTTP | `data` |
|---|---|---|
| No administrador / sin alcance | 403 | `{ "actorId", "roles" }` |
| Valor fuera de rango o tipo inválido | 400 | `{ "errores": [...], "versionActual" }` |
| Dependencia incumplida | 400 | `{ "errores": [{ "motivo": "dependencia" }] }` |
| Código desconocido | 400 | `{ "codigo", "modulo" }` |
| Parámetro de otro módulo | 400 | `{ "codigo", "modulo", "moduloPermitido" }` |
| `modulo` distinto de `autenticacion` | 400 | `{ "modulo", "moduloPermitido" }` |
| Versión inexistente | 404 | `{ "version" }` |

**Ninguna respuesta de error escribe:** la validación ocurre antes de calcular la nueva
versión y de insertar en el historial.

## Decisiones técnicas

1. **Versionamiento inmutable.** La tabla `auth_parameter_versions` solo admite
   `INSERT`: cada cambio guarda versión, `vigenteDesde`, actor, roles, motivo, valores
   nuevos y valores anteriores. No hay `UPDATE`/`DELETE`, por lo que el historial es
   consultable y no reescribible.
2. **Caché por versión.** `InMemoryAuthParametersCache` devuelve la instantánea solo si
   el número de versión coincide. El servicio explicita `invalidate()` tras cada
   escritura. Una versión nueva nunca puede servir datos de la anterior, incluso si dos
   instancias de la aplicación comparten proceso.
3. **Consumidores en la siguiente petición.** `AuthService` acepta un
   `AuthParametersProvider` opcional. En cada operación lee `AUT-01`, `AUT-02`,
   `AUT-03`, `AUT-04`, `AUT-05`, `AUT-06` y `AUT-07` a través de `value()`, que
   rescuela la versión vigente. Sin proveedor (pruebas antiguas o usos aislados) se
   mantiene el valor estático de `Settings`, por lo que no hay regresión.
4. **Auditoría.** Cada actualización registra un `AuditEvent` con entidad
   `parametros_autenticacion`, entidad `auth:version-N`, acción
   `parametros_actualizados`, actor y el diff de valores (anteriores vs. nuevos).
5. **Aislamiento por módulo.** El catálogo está etiquetado con `modulo=autenticacion`;
   los prefijos `CAT-` y `PROD-` se rechazan explícitamente y el campo `modulo` debe
   coincidir. El alcance `catalog.category.write` tampoco autoriza la escritura.

## Pruebas

```bash
pytest -q tests/test_auth_parameters_api.py
pytest -q
```

La suite cubre: consulta con versión y metadatos, actualización válida con auditoría,
rango inválido, tipo inválido, dependencias, petición vacía, productor 403, alcance de
otro módulo 403, alcance explícito 200, historial y versión inexistente, aislamiento de
módulos, código desconocido e invalidación de caché con efecto en un consumidor real.
