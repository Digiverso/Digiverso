# [HU-03] Perfil de usuario — implementación

**Módulo:** Autenticación · **Submódulo:** SUB-04 · **Funciones:** FUN-07, FUN-08
**Actor:** Consumidor, Productor · **Prioridad:** Media · **Puntos:** 3

### Historia de usuario

**Dado** un usuario autenticado,
**Para** que sus datos personales y su imagen estén actualizados,
**Que** consulte y edite su perfil sin poder modificar rol, correo verificado ni datos de otros usuarios.

| FUN | Proceso | Funcionalidad |
|---|---|---|
| FUN-07 | PRC-07 | Consultar perfil |
| FUN-08 | PRC-08 | Editar perfil |

## Endpoints

Base: `/api/v1/users`. Requieren `Authorization: Bearer <accessToken>` emitido por
`POST /api/v1/auth/login`. Todas las respuestas usan el sobre `message` / `data` / `success`.

| FUN | Método | Ruta | Resultado |
|---|---|---|---|
| FUN-07 | `GET` | `/users/me` | `200`, perfil del usuario autenticado |
| FUN-08 | `PATCH` | `/users/me` | `200`, perfil actualizado y auditado |
| — | `GET` / `PATCH` | `/users/{userId}` | `404`, no existe consulta de perfiles ajenos |

### GET `/users/me` (FUN-07)

Respuesta `200`:

```json
{
  "message": "Perfil consultado correctamente.",
  "data": {
    "id": "usr_001",
    "nombre": "Ana Torres",
    "correo": "ana@example.com",
    "rol": "consumidor",
    "biografia": "Ilustradora digital.",
    "foto": "https://cdn.digiverso.com/users/usr_001/foto-a1b2c3d4e5f6.png",
    "fechaRegistro": "2026-01-01T12:00:00+00:00"
  },
  "success": true
}
```

La respuesta nunca incluye `passwordHash`, tokens, intentos fallidos ni bloqueos.

### PATCH `/users/me` (FUN-08)

Acepta `application/json`:

```json
{
  "nombre": "Ana Torres",
  "biografia": "Ilustradora digital.",
  "foto": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="
}
```

También acepta `multipart/form-data` con `nombre`, `biografia` y `foto` como archivo.
`foto` puede ser un data URL base64, un archivo subido o una URL `http(s)` ya alojada
en CDN con extensión permitida. Respuesta `200`:

```json
{
  "message": "Perfil actualizado correctamente.",
  "data": {
    "id": "usr_001",
    "nombre": "Ana Torres",
    "correo": "ana@example.com",
    "rol": "consumidor",
    "biografia": "Ilustradora digital.",
    "foto": "https://cdn.digiverso.com/users/usr_001/foto-a1b2c3d4e5f6.png",
    "fechaRegistro": "2026-01-01T12:00:00+00:00"
  },
  "success": true
}
```

## Reglas de perfil

- Solo se pueden enviar `nombre`, `biografia` y `foto`. `rol`, `correo`, `estado`, `id`,
  `userId` y cualquier otro campo devuelven `400` con `data.campo`.
- El correo solo se cambia mediante el flujo separado de verificación; aquí es de solo lectura.
- El identificador del perfil siempre se toma del token y de la sesión activa asociada.
  No existe parámetro de usuario en la URL ni en el cuerpo.
- Un token expirado, con firma inválida o cuya sesión fue revocada devuelve `401`.
- `nombre`: 2 a 100 caracteres después de recortar espacios.
- `biografia`: hasta 500 caracteres; cadena vacía se normaliza a `null`.

## Foto (AUT-12)

- Tamaño máximo: **2 MiB** (`2097152` bytes), configurable con `AUT_12_MAX_BYTES`.
- Formatos permitidos: `jpeg`, `png` y `webp`, configurables con `AUT_12_ALLOWED_FORMATS`.
- El formato se detecta por los bytes reales de la imagen (firmas `FFD8FF`, PNG y RIFF/WEBP),
  no por la extensión del archivo ni por `Content-Type`.
- Si la imagen excede el tamaño o no coincide con una firma permitida, la respuesta es
  `400`, `data.campo = "foto"` y no se aplica ningún cambio ni auditoría.
- La clave generada es `users/{userId}/foto-{sha256[:12]}.{extension}` y la URL pública se
  construye con `PROFILE_PHOTO_CDN_BASE_URL`.

### Almacenamiento

Sin `PROFILE_PHOTO_BUCKET`, los bytes se guardan en `PROFILE_PHOTO_STORAGE_PATH` para
desarrollo y pruebas, pero la URL devuelta usa el formato CDN. Con bucket configurado se
usa S3 mediante `boto3` (dependencia opcional) y el objeto se sirve por CDN:

| Variable | Valor por defecto |
|---|---|
| `AUT_12_MAX_BYTES` | `2097152` |
| `AUT_12_ALLOWED_FORMATS` | `jpeg,png,webp` |
| `PROFILE_NAME_MIN_LENGTH` / `PROFILE_NAME_MAX_LENGTH` | `2` / `100` |
| `PROFILE_BIOGRAFIA_MAX_LENGTH` | `500` |
| `PROFILE_PHOTO_STORAGE_PATH` | `./uploads/profiles` |
| `PROFILE_PHOTO_CDN_BASE_URL` | `https://cdn.digiverso.com` |
| `PROFILE_PHOTO_BUCKET` | vacío (storage local) |
| `PROFILE_PHOTO_S3_REGION` | `us-east-1` |
| `PROFILE_PHOTO_S3_ENDPOINT` | vacío |

## Auditoría

Cada edición registra `perfil_actualizado` en `AuthRepository` con:

- `cuenta_id` y `metadata.usuario`: identificador del usuario.
- `registrado_en` y `metadata.fecha`: fecha de la operación.
- `metadata.campos`: lista de campos realmente modificados.
- `metadata.antes` y `metadata.despues`: valores de `nombre`, `biografia` y `foto`.
- `ip`: dirección de origen.

No se registran contraseñas, tokens ni datos de otros usuarios.

## Pruebas

`tests/test_users_api.py` cubre los cinco casos de la historia y controles adicionales:

1. Consulta de perfil propio y exclusión de campos sensibles.
2. Edición válida con nombre y biografía, respuesta actualizada y auditoría.
3. Foto mayor a AUT-12: `400`, sin cambios y sin auditoría.
4. Intento de cambiar `rol`, `correo`, `estado`, `id` o `userId`: `400` y valores intactos.
5. Perfil ajeno por URL o por cuerpo: `404` / `400`.
6. Foto válida por data URL, falso tipo de archivo, token ausente/inválido/revocado/expirado.
7. Documentación OpenAPI de `GET` y `PATCH /api/v1/users/me`.

Ejecución: `pytest -q`.
