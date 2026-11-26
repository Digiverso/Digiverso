# [HU-09] Medios del producto — implementación

**Módulo:** Catálogo · **Submódulo:** SUB-10 · **Funciones:** FUN-26, FUN-27
**Actor:** Productor · **Prioridad:** Media · **Puntos:** 3

### Historia de usuario

**Dado** un productor con un producto en borrador o publicado,
**Para** que el comprador vea el contenido con imágenes y videos de calidad,
**Que** cargue y elimine medios del producto respetando formatos, tamaños y cantidad.

**Beneficio esperado:** la ficha del producto es atractiva y confiable, y la
plataforma evita archivos inválidos o maliciosos.

| FUN | Proceso | Funcionalidad |
|---|---|---|
| FUN-26 | PRC-26 | Cargar medio |
| FUN-27 | PRC-27 | Eliminar medio |

## Endpoints

Base: `/api/v1/catalog/products`. Todas las respuestas —correctas e incorrectas—
usan el sobre `message` / `data` / `success`.

| FUN | Método | Ruta | Resultado |
|---|---|---|---|
| FUN-26 | `POST` | `/products/{id}/media` | `201`, medio asociado |
| FUN-27 | `DELETE` | `/products/{id}/media/{mediaId}` | `200`, borrado lógico y reordenamiento |

### POST `/products/{id}/media` (FUN-26)

Multipart/form-data. El campo esperado es `archivo` (también se acepta `file`):

```bash
curl -X POST http://localhost:8000/api/v1/catalog/products/prod_100/media \
  -H "X-Actor-Id: usr_010" \
  -F "archivo=@foto.png;type=image/png"
```

Respuesta `201`:

```json
{
  "message": "Medio cargado correctamente.",
  "data": {
    "id": "med_001",
    "productoId": "prod_100",
    "tipo": "imagen",
    "url": "https://cdn.digiverso.com/products/prod_100/med_001.png",
    "orden": 1,
    "estado": "activo"
  },
  "success": true
}
```

Cuando Pillow está disponible, la imagen se optimiza y se guarda como `.webp`;
si no lo está (o la imagen no es decodificable), se conserva el archivo ya
validado por firma con su extensión original. Los videos se almacenan sin
transcodificar: `MediaProcessor` es el punto de enganche con el worker
asíncrono.

### DELETE `/products/{id}/media/{mediaId}` (FUN-27)

Respuesta `200` (el medio queda con `estado = "eliminado"` y los visibles se
renumeran desde 1):

```json
{
  "message": "Medio eliminado correctamente.",
  "data": {
    "id": "med_002",
    "productoId": "prod_100",
    "estado": "eliminado",
    "totalMedios": 2,
    "medios": [
      { "id": "med_001", "tipo": "imagen", "url": "…", "orden": 1, "estado": "activo" },
      { "id": "med_003", "tipo": "video", "url": "…", "orden": 2, "estado": "activo" }
    ]
  },
  "success": true
}
```

## Reglas de negocio

CAT-05 a CAT-10 no tenían valores definidos en el repositorio (igual que ocurrió
con CAT-03/09/11/12/13 en HU-08). Se fijan en `app/core/config.py` y se pueden
sobreescribir desde `.env`:

| Regla | Código | Valor por defecto | Variable de entorno | Resultado |
|---|---|---|---|---|
| Formatos de imagen | CAT-05 | `jpg`, `jpeg`, `png`, `webp` | `CAT_05_IMAGE_FORMATS` | `400` |
| Tamaño máximo de imagen | CAT-06 | 10 MiB | `CAT_06_MAX_IMAGE_BYTES` | `413` |
| Formatos de video | CAT-07 | `mp4`, `m4v`, `mov`, `webm` | `CAT_07_VIDEO_FORMATS` | `400` |
| Tamaño máximo de video | CAT-08 | 200 MiB | `CAT_08_MAX_VIDEO_BYTES` | `413` |
| Máximo de medios por producto | CAT-10 | 10 | `CAT_10_MAX_MEDIA` | `409` |
| Medio inexistente o ya eliminado | — | — | — | `404` |
| Producto de otro autor | — | — | — | `403` |
| Producto en `en_revision` | — | — | — | `409` |
| Archivo que no pasa el escaneo | — | — | — | `400` (`MEDIA_SCAN_REJECTED`) |

GIF, PDF, ZIP, BMP y ejecutables quedan fuera en todos los casos. Los errores
incluyen `data.codigo` y, según el caso, `permitidos`, `tamanoBytes`,
`maximoBytes`, `actuales` o `maximo`.

### Orden de validación

1. Producto existente (`404`) y autoría (`403`).
2. Estado editable (`409`): `borrador`, `rechazado`, `publicado`, `archivado`.
3. Cantidad CAT-10 contando solo medios visibles (`409`).
4. Firma binaria, extensión y MIME coherentes (`400`).
5. Tamaño CAT-06/CAT-08 (`413`).
6. Escaneo (`400`).
7. Procesamiento, almacenamiento, persistencia y auditoría.

## Decisiones técnicas

- **Dominio:** `app/domain/media.py` concentra detección por firma, límites y
  reordenamiento. `app/domain/product.py` añade el campo `estado` a `Medio`
  (`activo`, `eliminado` y los estados de tránsito `en_analisis`/`rechazado`).
- **Firma real:** se comparan bytes en offsets fijos (JPEG, PNG, RIFF/WEBP,
  `ftyp`, marca `qt  ` para MOV, EBML para WebM). La extensión y el `Content-Type`
  solo se usan como comprobación de coherencia: no validan por sí solos.
- **Escaneo:** `SignatureFileScanner` rechaza EICAR, scripts incrustados, PE, ELF
  y shebangs. Está detrás del protocolo `FileScanner` para conectar un antivirus
  real. El escaneo ocurre **antes** de crear el medio activo o escribir el URL.
- **Borrado lógico y orden:** el medio eliminado permanece en el JSON del
  producto con `estado = "eliminado"`; no cuenta para CAT-10, no aparece en la
  ficha (`GET /products/{id}`) y los visibles pasan a `orden = 1..N`. La ficha
  pública (HU-10) devuelve los medios visibles ordenados por `orden`. El archivo
  físico se conserva.
- **Hash de contenido:** `Product.content()` ignora los medios eliminados, por
  lo que una eliminación se detecta como cambio al reactivar un producto
  archivado (HU-08).
- **Integración con HU-10:** la miniatura de la vitrina se deriva del primer
  medio visible, por lo que `MediaService` comparte el `ShowcaseCache` con
  `ProductService` y lo invalida al cargar o eliminar un medio.
- **Persistencia:** se reutiliza la columna `medios` de `productos` (JSON), sin
  migraciones nuevas. Los identificadores `med_XXX` se generan en
  `SQLiteProductRepository.next_media_id()`.
- **Almacenamiento:** `LocalMediaStorage` escribe en `MEDIA_STORAGE_DIR`
  (`uploads/media` por defecto, ignorado por Git) y compone URLs con
  `MEDIA_URL_BASE`. Se validan los segmentos de ruta para evitar traversal.
- **Auditoría:** eventos `cargar_medio` y `eliminar_medio` en `audit_log` con
  `entidad = "producto"`, actor, roles, fecha y detalle de medios/orden.

### Parámetros adicionales

| Variable | Valor por defecto | Uso |
|---|---|---|
| `MEDIA_STORAGE_DIR` | `uploads/media` | Directorio local de archivos |
| `MEDIA_URL_BASE` | `https://cdn.digiverso.com/products` | Prefijo de las URLs públicas |

### Dependencias

`python-multipart` es necesaria para multipart/form-data y se añadió a
`requirements.txt`. Pillow es opcional: si está instalada se usa para WebP.

## Pruebas

```bash
pytest -q
```

`tests/test_media_domain.py` cubre firmas, límites, conteo y reordenamiento;
`tests/test_media_api.py` cubre los cinco casos de la historia más autoría,
estado editable, extensión engañosa, escaneo, auditoría y la invalidación de la
vitrina de HU-10. Tras integrar HU-03/04/05/06 y HU-10, la suite completa
pasa con 162 pruebas.
