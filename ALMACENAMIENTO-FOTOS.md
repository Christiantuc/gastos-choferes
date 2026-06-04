# Almacenamiento permanente de fotos

En Render (plan gratis) el disco del servidor **se borra en cada deploy**. Para que las fotos no se pierdan, usá almacenamiento en la nube.

Recomendado: **Cloudflare R2** (gratis hasta ~10 GB, sin cargo por descarga).

---

## Paso 1 — Crear bucket en Cloudflare R2

1. Entrá a https://dash.cloudflare.com → **R2 Object Storage**
2. **Create bucket** → nombre: `gastos-fotos-choferes` (o el que prefieras)
3. En el bucket → **Settings** → anotá el nombre exacto

## Paso 2 — Crear claves de acceso

1. R2 → **Manage R2 API Tokens** → **Create API Token**
2. Permisos: **Object Read & Write** sobre el bucket
3. Copiá y guardá:
   - **Access Key ID**
   - **Secret Access Key**
4. Anotá también el **Account ID** de Cloudflare (en la URL o en R2 overview)

El endpoint será:

`https://TU_ACCOUNT_ID.r2.cloudflarestorage.com`

---

## Paso 3 — Variables en Render

En https://dashboard.render.com → tu servicio **gastos-choferes** → **Environment**:

| Variable | Valor |
|----------|--------|
| `STORAGE_BACKEND` | `s3` |
| `S3_BUCKET` | nombre del bucket (ej. `gastos-fotos-choferes`) |
| `S3_ACCESS_KEY_ID` | Access Key ID de R2 |
| `S3_SECRET_ACCESS_KEY` | Secret Access Key de R2 |
| `S3_ENDPOINT_URL` | `https://TU_ACCOUNT_ID.r2.cloudflarestorage.com` |
| `S3_REGION` | `auto` |

Guardá → Render hará un redeploy automático.

---

## Paso 4 — Probar

1. Un chofer sube una foto de prueba
2. Entrá como admin y verificá que se ve la imagen
3. Hacé un deploy nuevo desde GitHub
4. La foto **debe seguir visible** (ya no depende del disco de Render)

---

## Uso en PC local (desarrollo)

Sin variables de almacenamiento, las fotos se guardan en `data/uploads/` (comportamiento anterior).

Para probar R2 desde tu PC, copiá `.env.example` a `.env` y completá las mismas variables.

---

## Alternativa: AWS S3

Mismas variables, pero:

- `S3_ENDPOINT_URL` → dejarlo **vacío** (usa AWS por defecto)
- `S3_REGION` → ej. `sa-east-1` (São Paulo, más cerca de Argentina)

---

## Migración automática

Al arrancar con `STORAGE_BACKEND=s3`, la app **sube automáticamente** las fotos que existan en `data/uploads/` local hacia la nube (sin duplicar las que ya estén).
