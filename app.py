from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, Response, current_app
from datetime import datetime, timezone
import json
import os
import sys
import uuid
import shutil

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Ensure templates are found regardless of current working directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
os.chdir(BASE_DIR)

# Print debug information
print("\n=== Debug Information ===")
print(f"Python version: {sys.version}")
print(f"Current working directory: {os.getcwd()}")
print(f"Script directory: {os.path.dirname(os.path.abspath(__file__))}")
print(f"Templates directory: {TEMPLATES_DIR}")
print("Contents of templates directory:", os.listdir(TEMPLATES_DIR) if os.path.exists(TEMPLATES_DIR) else "Templates directory not found!")
print("======================\n")

# Ensure templates directory exists
os.makedirs(TEMPLATES_DIR, exist_ok=True)

app = Flask(__name__, template_folder=TEMPLATES_DIR)

app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
MASTER_PASSWORD = os.environ.get('MASTER_PASSWORD', 'master123')

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
EMPLOYEES_FILE = 'employees.json'
UPLOADS_META_FILE = 'uploads_meta.json'
AUDIT_LOG_FILE = 'audit_log.json'

# Empleados autorizados (DNI -> Nombre)
ALLOWED_EMPLOYEES = {
    '26684405': 'CANSINO ARIEL EDGARDO',
    '25862072': 'CARRIZO DIEGO FERNANDO',
    '25498853': 'GOMEZ JUAN RAFAEL',
    '25058170': 'LEYES OSVALDO OSCAR',
    '38216403': 'RUIZ JUAN MARTIN',
}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Max file size 10 MB
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

for path, default in [
    (EMPLOYEES_FILE, {}),
    (UPLOADS_META_FILE, []),
    (AUDIT_LOG_FILE, []),
]:
    if not os.path.exists(path):
        with open(path, 'w') as f:
            json.dump(default, f)

def read_json(path, default):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception:
        return default

def write_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def current_employee():
    dni = session.get('dni')
    if not dni:
        return None
    employees = read_json(EMPLOYEES_FILE, {})
    emp = employees.get(dni)
    if not emp:
        return None
    emp['dni'] = dni
    return emp

def current_admin():
    return True if session.get('is_admin') else False

def current_master():
    return True if session.get('is_master') else False

def total_for_dni(dni):
    uploads = [u for u in read_json(UPLOADS_META_FILE, []) if u.get('dni') == dni]
    total = 0.0
    for u in uploads:
        try:
            if u.get('amount') is not None:
                total += float(u.get('amount'))
        except Exception:
            continue
    return total

def log_activity(action, actor_role, actor_name=None, actor_dni=None, details=None):
    log = read_json(AUDIT_LOG_FILE, [])
    entry = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'action': action,
        'actor_role': actor_role,  # 'empleado' | 'admin' | 'master'
        'actor_name': actor_name,
        'actor_dni': actor_dni,
        'details': details or {}
    }
    log.append(entry)
    write_json(AUDIT_LOG_FILE, log)

def _parse_iso8601_z(ts: str):
    # Accept timestamps ending with 'Z' by replacing with +00:00
    try:
        if ts.endswith('Z'):
            ts = ts[:-1] + '+00:00'
        return datetime.fromisoformat(ts)
    except Exception:
        return None

@app.route('/')
def root():
    try:
        if session.get('is_admin'):
            return redirect(url_for('admin_dashboard'))
        if session.get('is_master'):
            return redirect(url_for('master_audit'))
        if session.get('dni'):
            return redirect(url_for('employee_home'))
        return redirect(url_for('login'))
    except Exception as e:
        print(f"Error en root: {str(e)}")
        return "Error al cargar la página principal. Por favor, intente nuevamente."

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        dni_raw = request.form.get('dni', '').strip()
        phone = request.form.get('phone', '').strip()
        # Normalizar DNI: dejar solo dígitos (elimina puntos/espacios)
        dni = ''.join(ch for ch in dni_raw if ch.isdigit())
        if not dni:
            return render_template('login.html', error='El DNI es obligatorio')
        # Validar DNI autorizado y obtener nombre
        employees = read_json(EMPLOYEES_FILE, {})
        emp = employees.get(dni) if isinstance(employees, dict) else None
        if emp:
            name = emp.get('name') or ''
            # actualizar/guardar teléfono si se envía
            employees[dni] = {**emp, 'name': name, 'phone': phone}
            write_json(EMPLOYEES_FILE, employees)
        else:
            # compatibilidad: permitir DNIs en la lista fija ALLOWED_EMPLOYEES
            name = ALLOWED_EMPLOYEES.get(dni)
            if not name:
                return render_template('login.html', error='DNI no autorizado')
            employees[dni] = {'name': name, 'phone': phone}
            write_json(EMPLOYEES_FILE, employees)
        session['dni'] = dni
        session.pop('is_admin', None)
        session.pop('is_master', None)
        os.makedirs(os.path.join(UPLOAD_FOLDER, dni), exist_ok=True)
        log_activity(
            action='login_empleado',
            actor_role='empleado',
            actor_name=name,
            actor_dni=dni,
            details={}
        )
        return redirect(url_for('employee_home'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    who = 'admin' if session.get('is_admin') else 'master' if session.get('is_master') else 'empleado'
    name = None
    dni = session.get('dni')
    if dni:
        emp = read_json(EMPLOYEES_FILE, {}).get(dni)
        name = emp.get('name') if emp else None
    session.clear()
    log_activity('logout', who, name, dni, {})
    return redirect(url_for('login'))

@app.route('/empleado')
def employee_home():
    emp = current_employee()
    if not emp:
        return redirect(url_for('login'))
    uploads = [u for u in read_json(UPLOADS_META_FILE, []) if u.get('dni') == emp['dni']]
    uploads.sort(key=lambda x: x.get('uploaded_at'), reverse=True)
    total = total_for_dni(emp['dni'])
    err = session.pop('error', None)
    return render_template('employee.html', employee=emp, uploads=uploads, total=total, error=err)

@app.route('/empleado/subir', methods=['POST'])
def employee_upload():
    emp = current_employee()
    if not emp:
        return redirect(url_for('login'))
    # Read extra fields
    amount_raw = request.form.get('amount', '').strip()
    category = request.form.get('category', '').strip() or 'Otros'
    date_str = request.form.get('date', '').strip()
    try:
        amount = float(amount_raw) if amount_raw else None
    except Exception:
        amount = None
    # Server-side validation of required fields
    if amount is None or category.strip() == '':
        session['error'] = 'Monto y Categoría son obligatorios para registrar el gasto con imagen.'
        return redirect(url_for('employee_home'))
    # Normalize date
    try:
        date_val = date_str if date_str else datetime.utcnow().date().isoformat()
    except Exception:
        date_val = datetime.utcnow().date().isoformat()
    # Corredor vial para categoría Peajes
    toll_corridor = (request.form.get('toll_corridor') or '').strip()
    if category == 'Peajes' and not toll_corridor:
        session['error'] = 'Debe seleccionar el corredor vial para categoría Peajes.'
        return redirect(url_for('employee_home'))
    # Empresa de combustible cuando la categoría es Combustible
    fuel_company = (request.form.get('fuel_company') or '').strip()
    if category == 'Combustible' and not fuel_company:
        session['error'] = 'Debe seleccionar la empresa de combustible.'
        return redirect(url_for('employee_home'))
    # N° Ticket requerido para Peajes y Combustible (ingresado por el empleado)
    ticket_number = (request.form.get('ticket_number') or '').strip()
    if category in ('Peajes', 'Combustible') and not ticket_number:
        session['error'] = 'Debe ingresar el N° Ticket para esta categoría.'
        return redirect(url_for('employee_home'))
    # Generar 'N° grabacion' persistente por empleado: últimos 6 dígitos del DNI + secuencia incremental
    employees_data = read_json(EMPLOYEES_FILE, {})
    emp_row = employees_data.get(emp['dni']) if isinstance(employees_data, dict) else None
    if not isinstance(emp_row, dict):
        emp_row = {}
    try:
        last_seq = int(emp_row.get('record_seq', -1))
    except Exception:
        last_seq = -1
    next_seq = last_seq + 1
    emp_row['record_seq'] = next_seq
    employees_data[emp['dni']] = emp_row
    write_json(EMPLOYEES_FILE, employees_data)
    grabacion_num = f"{emp['dni'][-6:]}{next_seq}"
    if 'file' not in request.files:
        return redirect(url_for('employee_home'))
    file = request.files['file']
    if file.filename == '':
        return redirect(url_for('employee_home'))
    if file and allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        uid = uuid.uuid4().hex
        fname = f"{uid}.{ext}"
        emp_dir = os.path.join(UPLOAD_FOLDER, emp['dni'])
        os.makedirs(emp_dir, exist_ok=True)
        dest_path = os.path.join(emp_dir, fname)
        file.save(dest_path)
        uploads = read_json(UPLOADS_META_FILE, [])
        uploads.append({
            'id': uid,
            'dni': emp['dni'],
            'filename': fname,
            'original_name': file.filename,
            'uploaded_at': datetime.utcnow().isoformat() + 'Z',
            'amount': amount,
            'category': category,
            'date': date_val,
            'toll_corridor': toll_corridor if category == 'Peajes' else None,
            'fuel_company': fuel_company if category == 'Combustible' else None,
            'ticket_number': ticket_number if category in ('Peajes','Combustible') else None,
            'N° grabacion': grabacion_num,
        })
        write_json(UPLOADS_META_FILE, uploads)
        # audit log
        log_activity(
            action='upload',
            actor_role='empleado',
            actor_name=emp.get('name'),
            actor_dni=emp.get('dni'),
            details={
                'filename': fname,
                'original_name': file.filename,
                'amount': amount,
                'category': category,
                'date': date_val
            }
        )
    return redirect(url_for('employee_home'))

@app.route('/files/<dni>/<filename>')
def serve_file(dni, filename):
    return send_from_directory(os.path.join(UPLOAD_FOLDER, dni), filename)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session.clear()
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        return render_template('admin_login.html', error='Clave incorrecta')
    return render_template('admin_login.html')

def require_admin():
    return session.get('is_admin') is True

def require_master():
    return session.get('is_master') is True

@app.route('/admin')
def admin_dashboard():
    if not require_admin():
        return redirect(url_for('admin_login'))
    employees = read_json(EMPLOYEES_FILE, {})
    uploads = read_json(UPLOADS_META_FILE, [])
    counts = {}
    totals = {}
    for u in uploads:
        dni = u['dni']
        counts[dni] = counts.get(dni, 0) + 1
        try:
            amt = float(u.get('amount')) if u.get('amount') is not None else 0.0
        except Exception:
            amt = 0.0
        totals[dni] = totals.get(dni, 0.0) + amt
    employees_list = [
        {
            'dni': dni,
            'name': data.get('name'),
            'phone': data.get('phone'),
            'count': counts.get(dni, 0),
            'total': totals.get(dni, 0.0)
        } for dni, data in employees.items()
    ]
    employees_list.sort(key=lambda x: x['name'] or '')
    return render_template('admin_dashboard.html', employees=employees_list)


@app.route('/admin/export')
def admin_export():
    if not require_admin():
        return redirect(url_for('admin_login'))
    employees = read_json(EMPLOYEES_FILE, {})
    uploads = read_json(UPLOADS_META_FILE, [])
    counts = {}
    totals = {}
    for u in uploads:
        dni = u.get('dni')
        if not dni:
            continue
        counts[dni] = counts.get(dni, 0) + 1
        try:
            amt = float(u.get('amount')) if u.get('amount') is not None else 0.0
        except Exception:
            amt = 0.0
        totals[dni] = totals.get(dni, 0.0) + amt
    employees_list = [
        {
            'dni': dni,
            'name': (data.get('name') if isinstance(data, dict) else None) or '',
            'phone': (data.get('phone') if isinstance(data, dict) else None) or '',
            'count': counts.get(dni, 0),
            'total': totals.get(dni, 0.0)
        } for dni, data in (employees.items() if isinstance(employees, dict) else [])
    ]
    employees_list.sort(key=lambda x: x['name'] or '')
    import csv
    from io import StringIO
    from flask import Response
    si = StringIO()
    si.write('\ufeff')
    si.write('sep=;\n')
    writer = csv.writer(si, delimiter=';')
    writer.writerow(['name','dni','phone','count','total'])
    for e in employees_list:
        try:
            total_str = '%.2f' % float(e.get('total') or 0.0)
        except Exception:
            total_str = ''
        writer.writerow([
            e.get('name') or '',
            e.get('dni') or '',
            e.get('phone') or '',
            e.get('count') or 0,
            total_str,
        ])
    output = si.getvalue()
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    return Response(
        output,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="admin_empleados_{ts}.csv"'}
    )


@app.route('/admin/export_grabaciones')
def admin_export_grabaciones():
    if not require_admin():
        return redirect(url_for('admin_login'))
    employees = read_json(EMPLOYEES_FILE, {})
    uploads = read_json(UPLOADS_META_FILE, [])
    # Preparar CSV Excel-friendly
    import csv
    from io import StringIO
    from flask import Response
    si = StringIO()
    si.write('\ufeff')
    si.write('sep=;\n')
    writer = csv.writer(si, delimiter=';')
    writer.writerow([
        'dni', 'name', 'N° grabacion', 'ticket_number', 'date', 'category',
        'fuel_company', 'toll_corridor', 'amount', 'uploaded_at', 'original_name', 'filename'
    ])
    if isinstance(uploads, list):
        for u in uploads:
            dni = u.get('dni') or ''
            emp = employees.get(dni) if isinstance(employees, dict) else None
            name = (emp.get('name') if isinstance(emp, dict) else None) or ''
            try:
                amount_str = '%.2f' % float(u.get('amount')) if u.get('amount') is not None else ''
            except Exception:
                amount_str = ''
            writer.writerow([
                dni,
                name,
                u.get('N° grabacion') or '',
                u.get('ticket_number') or '',
                u.get('date') or '',
                u.get('category') or '',
                u.get('fuel_company') or '',
                u.get('toll_corridor') or '',
                amount_str,
                u.get('uploaded_at') or '',
                u.get('original_name') or '',
                u.get('filename') or '',
            ])
    output = si.getvalue()
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    return Response(
        output,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="admin_grabaciones_{ts}.csv"'}
    )

@app.route('/admin/empleado/<dni>')
def admin_employee(dni):
    if not require_admin():
        return redirect(url_for('admin_login'))
    employees = read_json(EMPLOYEES_FILE, {})
    emp = employees.get(dni)
    if not emp:
        return redirect(url_for('admin_dashboard'))
    emp = {'dni': dni, **emp}
    uploads = [u for u in read_json(UPLOADS_META_FILE, []) if u.get('dni') == dni]
    uploads.sort(key=lambda x: x.get('uploaded_at'), reverse=True)
    total = total_for_dni(dni)
    return render_template('admin_employee.html', employee=emp, uploads=uploads, total=total)

@app.route('/admin/descargar/<dni>/<filename>')
def admin_download_file(dni, filename):
    if not require_admin():
        return redirect(url_for('admin_login'))
    # Try to use original name if exists and prefix with N° grabacion if present
    meta = next((u for u in read_json(UPLOADS_META_FILE, []) if u.get('dni') == dni and u.get('filename') == filename), None)
    base_name = meta.get('original_name') if meta and meta.get('original_name') else filename
    n_grab = meta.get('N° grabacion') if meta else None
    download_name = f"{n_grab} - {base_name}" if n_grab else base_name
    return send_from_directory(os.path.join(UPLOAD_FOLDER, dni), filename, as_attachment=True, download_name=download_name)

@app.route('/admin/descargar_todo/<dni>')
def admin_download_all(dni):
    if not require_admin():
        return redirect(url_for('admin_login'))
    from io import BytesIO
    import zipfile
    mem = BytesIO()
    with zipfile.ZipFile(mem, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
        uploads = [u for u in read_json(UPLOADS_META_FILE, []) if u.get('dni') == dni]
        for u in uploads:
            path = os.path.join(UPLOAD_FOLDER, dni, u.get('filename',''))
            if os.path.exists(path):
                base = u.get('original_name') or u.get('filename')
                n_grab = u.get('N° grabacion')
                arcname = f"{n_grab} - {base}" if n_grab else base
                # ensure unique names in zip
                zf.write(path, arcname=arcname)
    mem.seek(0)
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    return Response(mem.getvalue(), mimetype='application/zip', headers={'Content-Disposition': f'attachment; filename="{dni}_gastos_{ts}.zip"'})


@app.route('/admin/descargar_datos/<dni>')
def admin_download_data(dni):
    if not require_admin():
        return redirect(url_for('admin_login'))
    # Build simple HTML table Excel-compatible
    uploads = [u for u in read_json(UPLOADS_META_FILE, []) if u.get('dni') == dni]
    uploads.sort(key=lambda x: x.get('uploaded_at') or '')
    def esc(val):
        try:
            s = str(val) if val is not None else ''
            return (s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;'))
        except Exception:
            return ''
    rows = []
    rows.append('<tr><th>N° grabacion</th><th>Ticket</th><th>Fecha</th><th>Categoría</th><th>Combustible/Corredor</th><th>Monto</th></tr>')
    for u in uploads:
        n_grab = esc(u.get('N° grabacion') or '')
        ticket = esc(u.get('ticket_number') or '')
        fecha = esc(u.get('date') or '')
        categoria = esc(u.get('category') or '')
        comb_o_corr = esc(u.get('fuel_company') or u.get('toll_corridor') or '')
        try:
            monto = '%.2f' % float(u.get('amount')) if u.get('amount') is not None else ''
        except Exception:
            monto = ''
        rows.append(f"<tr><td>{n_grab}</td><td>{ticket}</td><td>{fecha}</td><td>{categoria}</td><td>{comb_o_corr}</td><td>{esc(monto)}</td></tr>")
    html = '<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><table border="1">' + ''.join(rows) + '</table></body></html>'
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    return Response(
        html,
        mimetype='application/vnd.ms-excel; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{dni}_datos_{ts}.xls"'}
    )

@app.route('/admin/eliminar_todo/<dni>', methods=['POST'])
def admin_delete_all(dni):
    if not require_admin():
        return redirect(url_for('admin_login'))
    uploads = read_json(UPLOADS_META_FILE, [])
    to_delete = [u for u in uploads if u.get('dni') == dni]
    # remove files
    for u in to_delete:
        file_path = os.path.join(UPLOAD_FOLDER, dni, u.get('filename', ''))
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass
    # update meta
    uploads = [u for u in uploads if u.get('dni') != dni]
    write_json(UPLOADS_META_FILE, uploads)
    log_activity('delete_all', 'admin', None, None, {'dni': dni, 'count': len(to_delete)})
    return redirect(url_for('admin_employee', dni=dni))

# Master user: login and audit view
@app.route('/master/login', methods=['GET', 'POST'])
def master_login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == MASTER_PASSWORD:
            session.clear()
            session['is_master'] = True
            return redirect(url_for('master_audit'))
        return render_template('master_login.html', error='Clave incorrecta')
    return render_template('master_login.html')

# Vista dedicada para gestionar empleados
@app.route('/master/empleados')
def master_employees():
    if not require_master():
        return redirect(url_for('master_login'))
    employees_data = read_json(EMPLOYEES_FILE, {})
    employees_list = [
        {'dni': dni, 'name': (data.get('name') if isinstance(data, dict) else None) or '', 'cuil': (data.get('cuil') if isinstance(data, dict) else None) or ''}
        for dni, data in employees_data.items()
    ]
    employees_list.sort(key=lambda x: x['name'] or '')
    return render_template(
        'master_audit.html',
        entries=[],
        start='',
        end='',
        dni='',
        action='',
        employees=employees_list,
        view='employees',
    )

# Alta de empleado por Master
@app.route('/master/empleados/agregar', methods=['POST'])
def master_add_employee():
    if not require_master():
        return redirect(url_for('master_login'))
    name = (request.form.get('name') or '').strip()
    dni_raw = (request.form.get('dni') or '').strip()
    cuil_raw = (request.form.get('cuil') or '').strip()
    # Normalizar DNI/CUIL a solo dígitos
    dni = ''.join(ch for ch in dni_raw if ch.isdigit())
    cuil = ''.join(ch for ch in cuil_raw if ch.isdigit())
    if not name or not dni or not cuil:
        # Podríamos pasar un mensaje de error vía querystring o flash; por simplicidad redirigimos
        return redirect(url_for('master_employees'))
    employees = read_json(EMPLOYEES_FILE, {})
    existing = employees.get(dni) if isinstance(employees, dict) else None
    phone = existing.get('phone') if isinstance(existing, dict) else None
    employees[dni] = {'name': name, 'phone': phone, 'cuil': cuil}
    write_json(EMPLOYEES_FILE, employees)
    log_activity('add_employee', 'master', None, None, {'dni': dni, 'name': name, 'cuil': cuil})
    return redirect(url_for('master_employees'))

@app.route('/master/empleados/editar', methods=['POST'])
def master_update_employee():
    if not require_master():
        return redirect(url_for('master_login'))
    original_dni = (request.form.get('original_dni') or '').strip()
    name = (request.form.get('name') or '').strip()
    new_dni_raw = (request.form.get('dni') or '').strip()
    new_cuil_raw = (request.form.get('cuil') or '').strip()
    # Normalizar DNI/CUIL
    new_dni = ''.join(ch for ch in new_dni_raw if ch.isdigit())
    new_cuil = ''.join(ch for ch in new_cuil_raw if ch.isdigit())
    if not original_dni:
        return redirect(url_for('master_employees'))
    if not name or not new_dni or not new_cuil:
        return redirect(url_for('master_employees'))
    employees = read_json(EMPLOYEES_FILE, {})
    existing = employees.get(original_dni) if isinstance(employees, dict) else None
    if not existing:
        return redirect(url_for('master_employees'))
    # Si cambia el DNI y ya existe otro con ese DNI, no continuar
    if new_dni != original_dni and new_dni in employees:
        return redirect(url_for('master_employees'))
    # Preparar datos nuevos conservando telefono si existiera
    phone = existing.get('phone') if isinstance(existing, dict) else None
    # Preservar campos adicionales (por ejemplo, record_seq)
    new_record = {**existing} if isinstance(existing, dict) else {}
    new_record.update({'name': name, 'phone': phone, 'cuil': new_cuil})
    # Migrar si cambia el DNI
    if new_dni != original_dni:
        employees[new_dni] = new_record
        if original_dni in employees:
            del employees[original_dni]
        write_json(EMPLOYEES_FILE, employees)
        # Actualizar uploads_meta.json
        uploads = read_json(UPLOADS_META_FILE, [])
        changed = False
        for u in uploads:
            if u.get('dni') == original_dni:
                u['dni'] = new_dni
                changed = True
        if changed:
            write_json(UPLOADS_META_FILE, uploads)
        # Mover carpeta de uploads
        try:
            old_dir = os.path.join(UPLOAD_FOLDER, original_dni)
            new_dir = os.path.join(UPLOAD_FOLDER, new_dni)
            if os.path.exists(old_dir):
                os.makedirs(os.path.dirname(new_dir) or UPLOAD_FOLDER, exist_ok=True)
                # Si ya existe new_dir, mover archivos individualmente
                if os.path.exists(new_dir):
                    for fname in os.listdir(old_dir):
                        try:
                            old_path = os.path.join(old_dir, fname)
                            new_path = os.path.join(new_dir, fname)
                            if os.path.exists(old_path):
                                # Asegurar nombre único si colisiona
                                if os.path.exists(new_path):
                                    base, ext = os.path.splitext(fname)
                                    import uuid as _uuid
                                    new_path = os.path.join(new_dir, f"{base}_{_uuid.uuid4().hex[:6]}{ext}")
                                shutil.move(old_path, new_path)
                        except Exception:
                            pass
                    try:
                        shutil.rmtree(old_dir, ignore_errors=True)
                    except Exception:
                        pass
                else:
                    shutil.move(old_dir, new_dir)
        except Exception:
            pass
        log_activity('update_employee', 'master', None, None, {
            'original_dni': original_dni,
            'new_dni': new_dni,
            'name': name,
            'cuil': new_cuil,
        })
    else:
        # Solo actualizar campos, preservando adicionales
        updated = {**existing} if isinstance(existing, dict) else {}
        updated.update({'name': name, 'phone': phone, 'cuil': new_cuil})
        employees[original_dni] = updated
        write_json(EMPLOYEES_FILE, employees)
        log_activity('update_employee', 'master', None, None, {
            'dni': original_dni,
            'name': name,
            'cuil': new_cuil,
        })
    return redirect(url_for('master_employees'))

def _format_ts(ts: str):
    dt = _parse_iso8601_z(ts) if ts else None
    if not dt:
        return ts or ''
    # dd/MM/yyyy HH:mm:ss
    return dt.strftime('%d/%m/%Y %H:%M:%S UTC')

def _filter_logs_by_date(entries, start_date_str=None, end_date_str=None):
    if not start_date_str and not end_date_str:
        return entries
    start_dt = None
    end_dt = None
    try:
        if start_date_str:
            start_dt = datetime.fromisoformat(start_date_str).replace(tzinfo=timezone.utc)
        if end_date_str:
            # include whole day end by moving to next day's 00:00 UTC (exclusive upper bound)
            from datetime import timedelta
            end_dt = datetime.fromisoformat(end_date_str).replace(tzinfo=timezone.utc) + timedelta(days=1)
    except Exception:
        start_dt = None
        end_dt = None
    filtered = []
    for e in entries:
        ts = e.get('timestamp')
        dt = _parse_iso8601_z(ts) if ts else None
        if not dt:
            continue
        ok = True
        if start_dt and dt < start_dt:
            ok = False
        if end_dt and dt >= end_dt:
            ok = False
        if ok:
            filtered.append(e)
    return filtered

@app.route('/master')
def master_audit():
    if not require_master():
        return redirect(url_for('master_login'))
    log = read_json(AUDIT_LOG_FILE, [])
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    actor_dni = request.args.get('dni', '').strip()
    action = request.args.get('action', '').strip()
    log = _filter_logs_by_date(log, start_date, end_date)
    if actor_dni:
        log = [e for e in log if (e.get('actor_dni') or '') == actor_dni]
    if action:
        log = [e for e in log if (e.get('action') or '') == action]
    log_sorted = sorted(log, key=lambda x: x.get('timestamp', ''), reverse=True)
    employees_data = read_json(EMPLOYEES_FILE, {})
    for entry in log_sorted:
        if not entry.get('actor_name') and entry.get('actor_dni'):
            emp = employees_data.get(entry['actor_dni'])
            if emp:
                entry['actor_name'] = emp.get('name')
        entry['ts_display'] = _format_ts(entry.get('timestamp'))
    employees_list = [
        {'dni': dni, 'name': (data.get('name') if isinstance(data, dict) else None) or ''}
        for dni, data in employees_data.items()
    ]
    employees_list.sort(key=lambda x: x['name'] or '')
    return render_template(
        'master_audit.html',
        entries=log_sorted,
        start=start_date or '',
        end=end_date or '',
        dni=actor_dni,
        action=action,
        employees=employees_list,
    )

@app.route('/master/export')
def master_export():
    if not require_master():
        return redirect(url_for('master_login'))
    fmt = request.args.get('format', 'json').lower()
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    actor_dni = request.args.get('dni', '').strip()
    action = request.args.get('action', '').strip()
    log = read_json(AUDIT_LOG_FILE, [])
    log = _filter_logs_by_date(log, start_date, end_date)
    if actor_dni:
        log = [e for e in log if (e.get('actor_dni') or '') == actor_dni]
    if action:
        log = [e for e in log if (e.get('action') or '') == action]
    # sort ascending for export
    log_sorted = sorted(log, key=lambda x: x.get('timestamp', ''))
    if fmt == 'csv':
        import csv
        from io import StringIO
        si = StringIO()
        writer = csv.writer(si)
        writer.writerow(['timestamp','action','actor_role','actor_name','actor_dni','n_grabacion','details'])
        for e in log_sorted:
            import json as _json
            details = e.get('details') or {}
            n_grab = details.get('N° grabacion') or ''
            writer.writerow([
                e.get('timestamp',''),
                e.get('action',''),
                e.get('actor_role',''),
                e.get('actor_name',''),
                e.get('actor_dni',''),
                n_grab,
                _json.dumps(details, ensure_ascii=False)
            ])
        from flask import Response
        output = si.getvalue()
        return Response(
            output,
            mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition': 'attachment; filename="audit_export.csv"'}
        )
    else:
        from flask import Response
        import json as _json
        output = _json.dumps(log_sorted, ensure_ascii=False, indent=2)
        return Response(
            output,
            mimetype='application/json; charset=utf-8',
            headers={'Content-Disposition': 'attachment; filename="audit_export.json"'}
        )


@app.route('/master/empleados/export')
def master_employees_export():
    if not require_master():
        return redirect(url_for('master_login'))
    employees = read_json(EMPLOYEES_FILE, {})
    import csv
    from io import StringIO
    from flask import Response
    si = StringIO()
    # Escribir BOM y directiva de separador para Excel
    si.write('\ufeff')
    si.write('sep=;\n')
    writer = csv.writer(si, delimiter=';')
    writer.writerow(['dni','name','cuil','phone','record_seq'])
    if isinstance(employees, dict):
        for dni, data in employees.items():
            if isinstance(data, dict):
                name = data.get('name') or ''
                cuil = data.get('cuil') or ''
                phone = data.get('phone') or ''
                record_seq = data.get('record_seq') if data.get('record_seq') is not None else ''
            else:
                name = ''
                cuil = ''
                phone = ''
                record_seq = ''
            writer.writerow([dni, name, cuil, phone, record_seq])
    output = si.getvalue()
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    return Response(
        output,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="empleados_{ts}.csv"'}
    )

def _delete_upload(upload_id=None, filename=None, requester_dni=None, admin=False):
    uploads = read_json(UPLOADS_META_FILE, [])
    target = None
    if upload_id:
        target = next((u for u in uploads if u.get('id') == upload_id), None)
    if not target and filename:
        target = next((u for u in uploads if u.get('filename') == filename), None)
    if not target:
        return False
    if not admin and requester_dni and target.get('dni') != requester_dni:
        return False
    # remove file
    file_path = os.path.join(UPLOAD_FOLDER, target.get('dni', ''), target.get('filename', ''))
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass
    # update meta
    if upload_id:
        uploads = [u for u in uploads if u.get('id') != upload_id]
    elif filename:
        uploads = [u for u in uploads if u.get('filename') != filename]
    write_json(UPLOADS_META_FILE, uploads)
    return True


def _delete_all_for_dni(dni: str):
    employees = read_json(EMPLOYEES_FILE, {})
    emp = employees.get(dni)
    # remove uploads meta and files
    uploads = read_json(UPLOADS_META_FILE, [])
    to_delete = [u for u in uploads if u.get('dni') == dni]
    for u in to_delete:
        file_path = os.path.join(UPLOAD_FOLDER, dni, u.get('filename', ''))
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass
    # remove directory if exists
    try:
        dir_path = os.path.join(UPLOAD_FOLDER, dni)
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path, ignore_errors=True)
    except Exception:
        pass
    # update uploads meta
    uploads = [u for u in uploads if u.get('dni') != dni]
    write_json(UPLOADS_META_FILE, uploads)
    # remove employee
    if dni in employees:
        del employees[dni]
        write_json(EMPLOYEES_FILE, employees)
    return emp.get('name') if isinstance(emp, dict) else None

@app.route('/master/empleados/eliminar', methods=['POST'])
def master_delete_employee_post():
    if not require_master():
        return redirect(url_for('master_login'))
    dni = request.form.get('dni', '').strip()
    if not dni:
        return redirect(url_for('master_audit'))
    name = _delete_all_for_dni(dni)
    log_activity('delete_employee', 'master', None, None, {
        'dni': dni,
        'employee_name': name,
    })
    return redirect(url_for('master_audit'))


@app.route('/empleado/eliminar', methods=['POST'])
def employee_delete_post():
    emp = current_employee()
    if not emp:
        return redirect(url_for('login'))
    upload_id = request.form.get('id')
    filename = request.form.get('filename')
    ok = _delete_upload(upload_id=upload_id, filename=filename, requester_dni=emp['dni'], admin=False)
    if ok:
        log_activity('delete', 'empleado', emp.get('name'), emp.get('dni'), {'id': upload_id, 'filename': filename})
    return redirect(url_for('employee_home'))

@app.route('/admin/eliminar/<upload_id>', methods=['POST'])
def admin_delete(upload_id):
    if not require_admin():
        return redirect(url_for('admin_login'))
    ok = _delete_upload(upload_id=upload_id, admin=True)
    if ok:
        log_activity('delete', 'admin', None, None, {'id': upload_id})
    # Try to get a dni param to redirect back
    dni = request.args.get('dni')
    if dni:
        return redirect(url_for('admin_employee', dni=dni))
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/eliminar', methods=['POST'])
def admin_delete_post():
    if not require_admin():
        return redirect(url_for('admin_login'))
    upload_id = request.form.get('id')
    filename = request.form.get('filename')
    dni = request.form.get('dni') or request.args.get('dni')
    ok = _delete_upload(upload_id=upload_id, filename=filename, admin=True)
    if ok:
        log_activity('delete', 'admin', None, None, {'id': upload_id, 'filename': filename, 'dni': dni})
    if dni:
        return redirect(url_for('admin_employee', dni=dni))
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    try:
        print("\n=== Iniciando servidor de la aplicación ===")
        print(f"Directorio de trabajo: {os.getcwd()}")
        print(f"Directorio de plantillas: {TEMPLATES_DIR}")
        print(f"Archivos en templates/: {os.listdir(TEMPLATES_DIR) if os.path.exists(TEMPLATES_DIR) else 'No existe'}")
        
        # Verify template files exist
        required_templates = ['login.html', 'admin_login.html', 'master_login.html']
        for template in required_templates:
            template_path = os.path.join(TEMPLATES_DIR, template)
            print(f"Checking {template} at {template_path}: {'Found' if os.path.exists(template_path) else 'MISSING'}")
        
        # Create missing templates if they don't exist
        login_template = os.path.join(TEMPLATES_DIR, 'login.html')
        if not os.path.exists(login_template):
            with open(login_template, 'w', encoding='utf-8') as f:
                f.write("""<!DOCTYPE html>
<html>
<head>
    <title>Login</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="container mt-5">
    <h1>Login</h1>
    {% if error %}<div class="alert alert-danger">{{ error }}</div>{% endif %}
    <form method="POST">
        <div class="mb-3">
            <label class="form-label">DNI</label>
            <input type="text" name="dni" class="form-control" required>
        </div>
        <div class="mb-3">
            <label class="form-label">Teléfono</label>
            <input type="tel" name="phone" class="form-control">
        </div>
        <button type="submit" class="btn btn-primary">Ingresar</button>
        <a href="{{ url_for('admin_login') }}" class="btn btn-secondary">Admin</a>
        <a href="{{ url_for('master_login') }}" class="btn btn-dark">Master</a>
    </form>
</body>
</html>""")
            print(f"Created missing template: {login_template}")
            
        admin_login_template = os.path.join(TEMPLATES_DIR, 'admin_login.html')
        if not os.path.exists(admin_login_template):
            with open(admin_login_template, 'w', encoding='utf-8') as f:
                f.write("""<!DOCTYPE html>
<html>
<head>
    <title>Admin Login</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="container mt-5">
    <h1>Admin Login</h1>
    {% if error %}<div class="alert alert-danger">{{ error }}</div>{% endif %}
    <form method="POST">
        <div class="mb-3">
            <label class="form-label">Contraseña</label>
            <input type="password" name="password" class="form-control" required>
        </div>
        <button type="submit" class="btn btn-primary">Ingresar</button>
        <a href="{{ url_for('login') }}" class="btn btn-secondary">Volver</a>
    </form>
</body>
</html>""")
            print(f"Created missing template: {admin_login_template}")
            
        master_login_template = os.path.join(TEMPLATES_DIR, 'master_login.html')
        if not os.path.exists(master_login_template):
            with open(master_login_template, 'w', encoding='utf-8') as f:
                f.write("""<!DOCTYPE html>
<html>
<head>
    <title>Master Login</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="container mt-5">
    <h1>Master Login</h1>
    {% if error %}<div class="alert alert-danger">{{ error }}</div>{% endif %}
    <form method="POST">
        <div class="mb-3">
            <label class="form-label">Contraseña Maestra</label>
            <input type="password" name="password" class="form-control" required>
        </div>
        <button type="submit" class="btn btn-primary">Ingresar</button>
        <a href="{{ url_for('login') }}" class="btn btn-secondary">Volver</a>
    </form>
</body>
</html>""")
            print(f"Created missing template: {master_login_template}")
        print(f"Directorio de plantillas: {TEMPLATES_DIR}")
        print(f"Carpeta de subidas: {os.path.abspath(UPLOAD_FOLDER)}")
        print("\nURLs disponibles:")
        print(f"- Página principal: http://localhost:5000/")
        print(f"- Login empleados: http://localhost:5000/login")
        print(f"- Admin login: http://localhost:5000/admin/login")
        print(f"- Master login: http://localhost:5000/master/login")
        print("\nPresiona Ctrl+C para detener el servidor\n")
        
        # Verificar si los archivos necesarios existen
        required_files = [EMPLOYEES_FILE, UPLOADS_META_FILE, AUDIT_LOG_FILE]
        for file in required_files:
            if not os.path.exists(file):
                with open(file, 'w') as f:
                    json.dump([] if file != EMPLOYEES_FILE else {}, f, indent=2)
                print(f"Archivo creado: {file}")
        
        # Crear carpeta de subidas si no existe
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        
        port = int(os.environ.get('PORT', 5000))
        debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
        app.run(host='0.0.0.0', port=port, debug=debug, use_reloader=False)
    except Exception as e:
        print(f"\n¡Error al iniciar el servidor!")
        print(f"Tipo de error: {type(e).__name__}")
        print(f"Mensaje: {str(e)}\n")
        print("Posibles soluciones:")
        print("1. Verifica que el puerto 5000 no esté en uso")
        print("2. Asegúrate de tener permisos de escritura en el directorio")
        print("3. Verifica que todos los archivos necesarios estén presentes")
        input("Presiona Enter para salir...")
