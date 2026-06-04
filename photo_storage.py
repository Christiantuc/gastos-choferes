"""Almacenamiento de fotos: disco local o nube S3-compatible (Cloudflare R2, AWS S3, etc.)."""
import mimetypes
import os
import shutil


def _object_key(dni: str, filename: str) -> str:
    return f"{dni}/{filename}"


def _guess_content_type(filename: str) -> str:
    ctype, _ = mimetypes.guess_type(filename)
    return ctype or 'application/octet-stream'


class LocalPhotoStorage:
    def __init__(self, root: str):
        self.root = root
        os.makedirs(root, exist_ok=True)

    @property
    def backend_name(self) -> str:
        return 'local'

    def save_bytes(self, dni: str, filename: str, data: bytes, content_type: str | None = None) -> None:
        dest_dir = os.path.join(self.root, dni)
        os.makedirs(dest_dir, exist_ok=True)
        with open(os.path.join(dest_dir, filename), 'wb') as f:
            f.write(data)

    def read_bytes(self, dni: str, filename: str) -> tuple[bytes | None, str]:
        path = os.path.join(self.root, dni, filename)
        if not os.path.exists(path):
            return None, _guess_content_type(filename)
        with open(path, 'rb') as f:
            return f.read(), _guess_content_type(filename)

    def exists(self, dni: str, filename: str) -> bool:
        return os.path.exists(os.path.join(self.root, dni, filename))

    def delete(self, dni: str, filename: str) -> None:
        path = os.path.join(self.root, dni, filename)
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    def delete_all_for_dni(self, dni: str) -> None:
        dir_path = os.path.join(self.root, dni)
        try:
            if os.path.exists(dir_path):
                shutil.rmtree(dir_path, ignore_errors=True)
        except OSError:
            pass

    def rename_dni(self, old_dni: str, new_dni: str) -> None:
        old_dir = os.path.join(self.root, old_dni)
        new_dir = os.path.join(self.root, new_dni)
        if not os.path.exists(old_dir):
            return
        os.makedirs(os.path.dirname(new_dir) or self.root, exist_ok=True)
        if os.path.exists(new_dir):
            for fname in os.listdir(old_dir):
                src = os.path.join(old_dir, fname)
                dst = os.path.join(new_dir, fname)
                if os.path.exists(dst):
                    base, ext = os.path.splitext(fname)
                    import uuid
                    dst = os.path.join(new_dir, f"{base}_{uuid.uuid4().hex[:6]}{ext}")
                shutil.move(src, dst)
            shutil.rmtree(old_dir, ignore_errors=True)
        else:
            shutil.move(old_dir, new_dir)

    def iter_local_files(self):
        if not os.path.isdir(self.root):
            return
        for dni in os.listdir(self.root):
            dni_dir = os.path.join(self.root, dni)
            if not os.path.isdir(dni_dir):
                continue
            for filename in os.listdir(dni_dir):
                path = os.path.join(dni_dir, filename)
                if os.path.isfile(path):
                    yield dni, filename, path


class S3PhotoStorage:
    def __init__(self, bucket: str, access_key: str, secret_key: str,
                 endpoint_url: str | None = None, region: str = 'auto'):
        import boto3
        from botocore.config import Config
        kwargs = {
            'aws_access_key_id': access_key,
            'aws_secret_access_key': secret_key,
            'region_name': region or 'auto',
            'config': Config(signature_version='s3v4'),
        }
        if endpoint_url:
            kwargs['endpoint_url'] = endpoint_url
        self.bucket = bucket
        self._client = boto3.client('s3', **kwargs)

    @property
    def backend_name(self) -> str:
        return 's3'

    def save_bytes(self, dni: str, filename: str, data: bytes, content_type: str | None = None) -> None:
        self._client.put_object(
            Bucket=self.bucket,
            Key=_object_key(dni, filename),
            Body=data,
            ContentType=content_type or _guess_content_type(filename),
        )

    def read_bytes(self, dni: str, filename: str) -> tuple[bytes | None, str]:
        from botocore.exceptions import ClientError
        try:
            resp = self._client.get_object(Bucket=self.bucket, Key=_object_key(dni, filename))
            body = resp['Body'].read()
            ctype = resp.get('ContentType') or _guess_content_type(filename)
            return body, ctype
        except ClientError as exc:
            code = exc.response.get('Error', {}).get('Code', '')
            if code in ('NoSuchKey', '404', 'NotFound'):
                return None, _guess_content_type(filename)
            raise

    def exists(self, dni: str, filename: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=_object_key(dni, filename))
            return True
        except Exception:
            return False

    def delete(self, dni: str, filename: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=_object_key(dni, filename))
        except Exception:
            pass

    def delete_all_for_dni(self, dni: str) -> None:
        prefix = f"{dni}/"
        token = None
        while True:
            kwargs = {'Bucket': self.bucket, 'Prefix': prefix}
            if token:
                kwargs['ContinuationToken'] = token
            resp = self._client.list_objects_v2(**kwargs)
            contents = resp.get('Contents') or []
            if contents:
                self._client.delete_objects(
                    Bucket=self.bucket,
                    Delete={'Objects': [{'Key': obj['Key']} for obj in contents]},
                )
            if not resp.get('IsTruncated'):
                break
            token = resp.get('NextContinuationToken')

    def rename_dni(self, old_dni: str, new_dni: str) -> None:
        prefix = f"{old_dni}/"
        token = None
        while True:
            kwargs = {'Bucket': self.bucket, 'Prefix': prefix}
            if token:
                kwargs['ContinuationToken'] = token
            resp = self._client.list_objects_v2(**kwargs)
            for obj in resp.get('Contents') or []:
                old_key = obj['Key']
                filename = old_key.split('/', 1)[1]
                new_key = _object_key(new_dni, filename)
                self._client.copy_object(
                    Bucket=self.bucket,
                    CopySource={'Bucket': self.bucket, 'Key': old_key},
                    Key=new_key,
                )
                self._client.delete_object(Bucket=self.bucket, Key=old_key)
            if not resp.get('IsTruncated'):
                break
            token = resp.get('NextContinuationToken')


def create_photo_storage(local_root: str):
    backend = (os.environ.get('STORAGE_BACKEND') or 'local').strip().lower()
    if backend in ('s3', 'r2', 'cloud'):
        bucket = os.environ.get('S3_BUCKET', '').strip()
        access_key = os.environ.get('S3_ACCESS_KEY_ID', '').strip()
        secret_key = os.environ.get('S3_SECRET_ACCESS_KEY', '').strip()
        if not bucket or not access_key or not secret_key:
            raise RuntimeError(
                'STORAGE_BACKEND=s3 requiere S3_BUCKET, S3_ACCESS_KEY_ID y S3_SECRET_ACCESS_KEY'
            )
        return S3PhotoStorage(
            bucket=bucket,
            access_key=access_key,
            secret_key=secret_key,
            endpoint_url=os.environ.get('S3_ENDPOINT_URL', '').strip() or None,
            region=os.environ.get('S3_REGION', 'auto').strip() or 'auto',
        )
    return LocalPhotoStorage(local_root)


def migrate_local_to_cloud(local_root: str, remote_storage) -> int:
    """Sube fotos locales a la nube (una sola vez). Devuelve cantidad migrada."""
    if remote_storage.backend_name == 'local':
        return 0
    local = LocalPhotoStorage(local_root)
    migrated = 0
    for dni, filename, path in local.iter_local_files():
        if remote_storage.exists(dni, filename):
            continue
        with open(path, 'rb') as f:
            data = f.read()
        remote_storage.save_bytes(dni, filename, data, _guess_content_type(filename))
        migrated += 1
    return migrated
