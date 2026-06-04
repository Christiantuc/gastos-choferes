"""Persistencia en SQLite dentro de DATA_DIR. En producción respalda la BD en R2."""
import json
import os
import shutil
import sqlite3
import threading

_lock = threading.Lock()
_conn = None
_data_dir = None
_db_path = None
CLOUD_DB_KEY = 'meta/gastos.db'
SEED_MARKER = '.seed_complete'


def _cloud_enabled() -> bool:
    backend = (os.environ.get('STORAGE_BACKEND') or 'local').strip().lower()
    if backend not in ('s3', 'r2', 'cloud'):
        return False
    return bool(
        os.environ.get('S3_BUCKET')
        and os.environ.get('S3_ACCESS_KEY_ID')
        and os.environ.get('S3_SECRET_ACCESS_KEY')
    )


def _s3_client():
    import boto3
    from botocore.config import Config
    kwargs = {
        'aws_access_key_id': os.environ.get('S3_ACCESS_KEY_ID', '').strip(),
        'aws_secret_access_key': os.environ.get('S3_SECRET_ACCESS_KEY', '').strip(),
        'region_name': os.environ.get('S3_REGION', 'auto').strip() or 'auto',
        'config': Config(signature_version='s3v4'),
    }
    endpoint = os.environ.get('S3_ENDPOINT_URL', '').strip()
    if endpoint:
        kwargs['endpoint_url'] = endpoint
    return boto3.client('s3', **kwargs)


def _restore_db_from_cloud():
    if not _cloud_enabled() or not _db_path:
        return False
    try:
        client = _s3_client()
        bucket = os.environ.get('S3_BUCKET', '').strip()
        client.download_file(bucket, CLOUD_DB_KEY, _db_path)
        return os.path.exists(_db_path) and os.path.getsize(_db_path) > 0
    except Exception:
        return False


def backup_db_to_cloud():
    """Sube gastos.db a R2 después de cada cambio."""
    if not _cloud_enabled() or not _db_path or not os.path.exists(_db_path):
        return
    try:
        with _lock:
            if _conn:
                _conn.commit()
            client = _s3_client()
            bucket = os.environ.get('S3_BUCKET', '').strip()
            client.upload_file(_db_path, bucket, CLOUD_DB_KEY)
    except Exception as exc:
        print(f"AVISO: no se pudo respaldar la BD en la nube: {exc}")


def init_storage(base_dir: str, data_dir: str | None = None):
    global _conn, _data_dir, _db_path
    if data_dir is None:
        data_dir = os.environ.get('DATA_DIR', os.path.join(base_dir, 'data'))
    os.makedirs(data_dir, exist_ok=True)
    _data_dir = data_dir
    _db_path = os.path.join(data_dir, 'gastos.db')

    had_local_db = os.path.exists(_db_path) and os.path.getsize(_db_path) > 0
    if not had_local_db:
        _restore_db_from_cloud()

    _conn = sqlite3.connect(_db_path, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.execute('PRAGMA journal_mode=WAL')
    _conn.execute('PRAGMA foreign_keys=ON')
    _create_tables()
    _migrate_from_json(base_dir)
    return data_dir


def _create_tables():
    _conn.executescript('''
        CREATE TABLE IF NOT EXISTS employees (
            dni TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT,
            cuil TEXT,
            record_seq INTEGER DEFAULT -1
        );
        CREATE TABLE IF NOT EXISTS uploads (
            id TEXT PRIMARY KEY,
            dni TEXT NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT,
            uploaded_at TEXT NOT NULL,
            amount REAL,
            category TEXT,
            date TEXT,
            toll_corridor TEXT,
            fuel_company TEXT,
            ticket_number TEXT,
            grabacion TEXT
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action TEXT NOT NULL,
            actor_role TEXT,
            actor_name TEXT,
            actor_dni TEXT,
            details TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_uploads_dni ON uploads(dni);
        CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(timestamp);
    ''')
    _conn.commit()


def _load_json_file(path):
    for encoding in ('utf-8', 'latin-1'):
        try:
            with open(path, 'r', encoding=encoding) as f:
                return json.load(f)
        except (UnicodeDecodeError, json.JSONDecodeError, OSError):
            continue
    return None


def _migrate_from_json(base_dir: str):
    """Solo la primera vez: importa JSON del repo si no hay BD en la nube."""
    marker = os.path.join(_data_dir, SEED_MARKER)
    if os.path.exists(marker):
        return

    had_data = (
        _conn.execute('SELECT COUNT(*) FROM employees').fetchone()[0] > 0
        or _conn.execute('SELECT COUNT(*) FROM uploads').fetchone()[0] > 0
    )
    if had_data:
        with open(marker, 'w') as f:
            f.write('1')
        backup_db_to_cloud()
        return

    employees_path = os.path.join(base_dir, 'employees.json')
    uploads_path = os.path.join(base_dir, 'uploads_meta.json')
    audit_path = os.path.join(base_dir, 'audit_log.json')

    employees = _load_json_file(employees_path) if os.path.exists(employees_path) else None
    if isinstance(employees, dict):
        for dni, data in employees.items():
            if isinstance(data, dict):
                save_employee(dni, data)

    uploads = _load_json_file(uploads_path) if os.path.exists(uploads_path) else None
    if isinstance(uploads, list):
        for u in uploads:
            if isinstance(u, dict) and u.get('id'):
                add_upload(u)

    log = _load_json_file(audit_path) if os.path.exists(audit_path) else None
    if isinstance(log, list):
        for entry in log:
            if isinstance(entry, dict):
                _insert_audit(entry)
    _conn.commit()

    with open(marker, 'w') as f:
        f.write('1')
    backup_db_to_cloud()


def _after_write():
    backup_db_to_cloud()


def get_employees() -> dict:
    rows = _conn.execute('SELECT * FROM employees').fetchall()
    result = {}
    for row in rows:
        result[row['dni']] = {
            'name': row['name'],
            'phone': row['phone'],
            'cuil': row['cuil'],
            'record_seq': row['record_seq'],
        }
    return result


def get_employee(dni: str) -> dict | None:
    row = _conn.execute('SELECT * FROM employees WHERE dni = ?', (dni,)).fetchone()
    if not row:
        return None
    return {
        'name': row['name'],
        'phone': row['phone'],
        'cuil': row['cuil'],
        'record_seq': row['record_seq'],
    }


def save_employee(dni: str, data: dict):
    with _lock:
        _conn.execute('''
            INSERT INTO employees (dni, name, phone, cuil, record_seq)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(dni) DO UPDATE SET
                name = excluded.name,
                phone = COALESCE(excluded.phone, employees.phone),
                cuil = COALESCE(excluded.cuil, employees.cuil),
                record_seq = COALESCE(excluded.record_seq, employees.record_seq)
        ''', (
            dni,
            data.get('name', ''),
            data.get('phone'),
            data.get('cuil'),
            data.get('record_seq', -1),
        ))
        _conn.commit()
    _after_write()


def delete_employee(dni: str):
    with _lock:
        _conn.execute('DELETE FROM employees WHERE dni = ?', (dni,))
        _conn.commit()
    _after_write()


def next_record_seq(dni: str) -> int:
    with _lock:
        row = _conn.execute('SELECT record_seq FROM employees WHERE dni = ?', (dni,)).fetchone()
        last_seq = row['record_seq'] if row else -1
        try:
            last_seq = int(last_seq)
        except (TypeError, ValueError):
            last_seq = -1
        next_seq = last_seq + 1
        _conn.execute('UPDATE employees SET record_seq = ? WHERE dni = ?', (next_seq, dni))
        _conn.commit()
    _after_write()
    return next_seq


def get_uploads(dni: str | None = None) -> list:
    if dni:
        rows = _conn.execute(
            'SELECT * FROM uploads WHERE dni = ? ORDER BY uploaded_at DESC', (dni,)
        ).fetchall()
    else:
        rows = _conn.execute('SELECT * FROM uploads ORDER BY uploaded_at DESC').fetchall()
    return [_row_to_upload(row) for row in rows]


def _row_to_upload(row) -> dict:
    u = {
        'id': row['id'],
        'dni': row['dni'],
        'filename': row['filename'],
        'original_name': row['original_name'],
        'uploaded_at': row['uploaded_at'],
        'amount': row['amount'],
        'category': row['category'],
        'date': row['date'],
        'toll_corridor': row['toll_corridor'],
        'fuel_company': row['fuel_company'],
        'ticket_number': row['ticket_number'],
    }
    if row['grabacion']:
        u['N° grabacion'] = row['grabacion']
    return u


def add_upload(record: dict):
    with _lock:
        _conn.execute('''
            INSERT OR REPLACE INTO uploads
            (id, dni, filename, original_name, uploaded_at, amount, category, date,
             toll_corridor, fuel_company, ticket_number, grabacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            record['id'],
            record['dni'],
            record['filename'],
            record.get('original_name'),
            record['uploaded_at'],
            record.get('amount'),
            record.get('category'),
            record.get('date'),
            record.get('toll_corridor'),
            record.get('fuel_company'),
            record.get('ticket_number'),
            record.get('N° grabacion'),
        ))
        _conn.commit()
    _after_write()


def update_upload_dni(old_dni: str, new_dni: str):
    with _lock:
        _conn.execute('UPDATE uploads SET dni = ? WHERE dni = ?', (new_dni, old_dni))
        _conn.commit()
    _after_write()


def delete_upload_by_id(upload_id: str) -> dict | None:
    row = _conn.execute('SELECT * FROM uploads WHERE id = ?', (upload_id,)).fetchone()
    if not row:
        return None
    with _lock:
        _conn.execute('DELETE FROM uploads WHERE id = ?', (upload_id,))
        _conn.commit()
    _after_write()
    return _row_to_upload(row)


def delete_upload_by_filename(filename: str, dni: str | None = None) -> dict | None:
    if dni:
        row = _conn.execute(
            'SELECT * FROM uploads WHERE filename = ? AND dni = ?', (filename, dni)
        ).fetchone()
    else:
        row = _conn.execute('SELECT * FROM uploads WHERE filename = ?', (filename,)).fetchone()
    if not row:
        return None
    with _lock:
        if dni:
            _conn.execute('DELETE FROM uploads WHERE filename = ? AND dni = ?', (filename, dni))
        else:
            _conn.execute('DELETE FROM uploads WHERE filename = ?', (filename,))
        _conn.commit()
    _after_write()
    return _row_to_upload(row)


def delete_uploads_for_dni(dni: str) -> list:
    rows = _conn.execute('SELECT * FROM uploads WHERE dni = ?', (dni,)).fetchall()
    with _lock:
        _conn.execute('DELETE FROM uploads WHERE dni = ?', (dni,))
        _conn.commit()
    _after_write()
    return [_row_to_upload(row) for row in rows]


def find_upload(dni: str, filename: str) -> dict | None:
    row = _conn.execute(
        'SELECT * FROM uploads WHERE dni = ? AND filename = ?', (dni, filename)
    ).fetchone()
    return _row_to_upload(row) if row else None


def _insert_audit(entry: dict):
    details = entry.get('details')
    if isinstance(details, dict):
        details = json.dumps(details, ensure_ascii=False)
    _conn.execute('''
        INSERT INTO audit_log (timestamp, action, actor_role, actor_name, actor_dni, details)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        entry.get('timestamp', ''),
        entry.get('action', ''),
        entry.get('actor_role'),
        entry.get('actor_name'),
        entry.get('actor_dni'),
        details,
    ))


def append_audit(entry: dict):
    with _lock:
        _insert_audit(entry)
        _conn.commit()
    _after_write()


def get_audit_log() -> list:
    rows = _conn.execute('SELECT * FROM audit_log ORDER BY timestamp DESC').fetchall()
    result = []
    for row in rows:
        details = row['details']
        if details:
            try:
                details = json.loads(details)
            except json.JSONDecodeError:
                pass
        result.append({
            'timestamp': row['timestamp'],
            'action': row['action'],
            'actor_role': row['actor_role'],
            'actor_name': row['actor_name'],
            'actor_dni': row['actor_dni'],
            'details': details or {},
        })
    return result
