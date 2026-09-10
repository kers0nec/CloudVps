"""CloudVPS — a real, Docker-backed VPS control panel.

A small Flask API + single-page dashboard. Every VPS is a real Docker
container provisioned by ``docker_utils``; this module owns authentication,
ownership metadata and the HTTP surface. No fake/placeholder data is stored.
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import random
import string
import os
import threading

import docker_utils as vps_engine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'vps.db')
_db_lock = threading.Lock()

app = Flask(__name__)
CORS(app)


# ============================ DATABASE ============================
def init_db():
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE,
                password_hash TEXT,
                api_key TEXT UNIQUE,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS vps_instances (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                name TEXT,
                plan TEXT,
                status TEXT DEFAULT 'running',
                cpu TEXT,
                memory TEXT,
                storage TEXT,
                ip TEXT,
                container_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')

        # Forward-compatible migrations for existing databases.
        vps_cols = [r[1] for r in c.execute('PRAGMA table_info(vps_instances)')]
        if 'container_id' not in vps_cols:
            c.execute('ALTER TABLE vps_instances ADD COLUMN container_id TEXT')
        user_cols = [r[1] for r in c.execute('PRAGMA table_info(users)')]
        if 'password_hash' not in user_cols:
            c.execute('ALTER TABLE users ADD COLUMN password_hash TEXT')

        conn.commit()
        conn.close()


init_db()


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# ============================ HELPERS ============================
def generate_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))


def generate_api_key():
    return 'vps_' + ''.join(random.choices(string.hexdigits, k=48))


def get_plans():
    return vps_engine.PLANS


def error(message, code=400):
    return jsonify({'error': message}), code


def auth_required(f):
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if not api_key:
            return error('API key required', 401)
        conn = get_db()
        user = conn.execute(
            'SELECT * FROM users WHERE api_key = ?', (api_key,)
        ).fetchone()
        conn.close()
        if not user:
            return error('Invalid API key', 401)
        request.user = dict(user)
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated


def handle_engine(exc):
    """Translate engine errors into HTTP responses."""
    msg = str(exc)
    if 'Docker is not available' in msg:
        return error(
            'VPS backend (Docker) is not reachable. Start the Docker daemon '
            'and ensure this app can talk to it.', 503
        )
    return error(f'VPS operation failed: {msg}', 500)


def refresh_vps_row(conn, row):
    """Sync a DB row's status/ip from the real container; drop orphan rows."""
    cid = row['container_id']
    if not cid:
        return row
    try:
        container = vps_engine.get_container(cid)
        snap = vps_engine.describe(container)
        conn.execute(
            'UPDATE vps_instances SET status = ?, ip = ? WHERE id = ?',
            (snap['status'], snap['ip'], row['id']),
        )
        updated = dict(row)
        updated['status'] = snap['status']
        updated['ip'] = snap['ip']
        return updated
    except Exception as exc:  # noqa: BLE001
        if 'not found' in str(exc).lower() or 'no such container' in str(exc).lower():
            # Real container is gone — reflect reality in the database.
            conn.execute('DELETE FROM vps_instances WHERE id = ?', (row['id'],))
            return None
        # Docker unreachable: keep stored values, cannot verify.
        return row


# ============================ DASHBOARD ============================
@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/api/health')
def health():
    docker_ok = True
    try:
        vps_engine.get_client().ping()
    except Exception:
        docker_ok = False
    return jsonify({'status': 'ok', 'docker': docker_ok})


# ============================ AUTH ============================
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return error('Username and password required')
    if len(password) < 6:
        return error('Password must be at least 6 characters')

    user_id = generate_id()
    api_key = generate_api_key()

    with _db_lock:
        conn = get_db()
        try:
            conn.execute(
                'INSERT INTO users (id, username, password_hash, api_key) '
                'VALUES (?, ?, ?, ?)',
                (user_id, username, generate_password_hash(password), api_key),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return error('Username already exists')
        conn.close()

    return jsonify({
        'success': True,
        'api_key': api_key,
        'user_id': user_id,
        'username': username,
    })


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return error('Username and password required')

    conn = get_db()
    user = conn.execute(
        'SELECT * FROM users WHERE username = ?', (username,)
    ).fetchone()
    conn.close()

    if not user or not check_password_hash(user['password_hash'], password):
        return error('Invalid credentials', 401)

    return jsonify({
        'success': True,
        'api_key': user['api_key'],
        'user_id': user['id'],
        'username': user['username'],
    })


@app.route('/api/plans', methods=['GET'])
def plans():
    return jsonify(get_plans())


# ============================ VPS ============================
@app.route('/api/vps', methods=['POST'])
@auth_required
def create_vps():
    data = request.get_json(silent=True) or {}
    plan = data.get('plan', 'starter')
    name = (data.get('name') or '').strip() or f"vps-{generate_id()[:6]}"

    plans = get_plans()
    if plan not in plans:
        return error('Invalid plan. Options: ' + ', '.join(plans.keys()))

    config = plans[plan]
    vps_id = generate_id()

    # Provision the REAL container first, then record ownership.
    try:
        created = vps_engine.create_vps_container(request.user['id'], plan)
    except Exception as exc:  # noqa: BLE001
        return handle_engine(exc)

    with _db_lock:
        conn = get_db()
        try:
            conn.execute(
                'INSERT INTO vps_instances '
                '(id, user_id, name, plan, status, cpu, memory, storage, ip, '
                'container_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (vps_id, request.user['id'], name, plan, created['status'],
                 config['cpu'], config['memory'], config['storage'],
                 created['ip'], created['container_id']),
            )
            conn.commit()
        except Exception:
            # Roll back the real container if we can't record it.
            try:
                vps_engine.delete_container(created['container_id'])
            except Exception:
                pass
            conn.close()
            return error('Failed to record VPS', 500)
        conn.close()

    return jsonify({
        'success': True,
        'vps': {
            'id': vps_id,
            'container_id': created['container_id'],
            'name': name,
            'plan': plan,
            'status': created['status'],
            'cpu': config['cpu'],
            'memory': config['memory'],
            'storage': config['storage'],
            'ip': created['ip'],
        }
    }), 201


@app.route('/api/vps', methods=['GET'])
@auth_required
def list_vps():
    with _db_lock:
        conn = get_db()
        rows = conn.execute(
            'SELECT * FROM vps_instances WHERE user_id = ? '
            'ORDER BY created_at DESC',
            (request.user['id'],),
        ).fetchall()
        # Re-sync with reality; collect survivors.
        survivors = []
        for row in rows:
            synced = refresh_vps_row(conn, dict(row))
            if synced is not None:
                survivors.append(synced)
        conn.commit()
        conn.close()

    return jsonify({'success': True, 'vps': [dict(r) for r in survivors]})


@app.route('/api/vps/<vps_id>', methods=['GET'])
@auth_required
def get_vps(vps_id):
    conn = get_db()
    row = conn.execute(
        'SELECT * FROM vps_instances WHERE id = ? AND user_id = ?',
        (vps_id, request.user['id']),
    ).fetchone()
    conn.close()
    if not row:
        return error('VPS not found', 404)
    return jsonify({'success': True, 'vps': dict(row)})


def _own_row(vps_id):
    """Fetch a user-owned VPS row or return (None, response)."""
    conn = get_db()
    row = conn.execute(
        'SELECT * FROM vps_instances WHERE id = ? AND user_id = ?',
        (vps_id, request.user['id']),
    ).fetchone()
    conn.close()
    if not row:
        return None, error('VPS not found', 404)
    return row, None


@app.route('/api/vps/<vps_id>/start', methods=['POST'])
@auth_required
def start_vps(vps_id):
    row, resp = _own_row(vps_id)
    if resp:
        return resp
    try:
        status = vps_engine.start_container(row['container_id'])
    except Exception as exc:  # noqa: BLE001
        return handle_engine(exc)
    conn = get_db()
    conn.execute('UPDATE vps_instances SET status = ? WHERE id = ?',
                 (status, vps_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'status': status})


@app.route('/api/vps/<vps_id>/stop', methods=['POST'])
@auth_required
def stop_vps(vps_id):
    row, resp = _own_row(vps_id)
    if resp:
        return resp
    try:
        status = vps_engine.stop_container(row['container_id'])
    except Exception as exc:  # noqa: BLE001
        return handle_engine(exc)
    conn = get_db()
    conn.execute('UPDATE vps_instances SET status = ? WHERE id = ?',
                 (status, vps_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'status': status})


@app.route('/api/vps/<vps_id>', methods=['DELETE'])
@auth_required
def delete_vps(vps_id):
    row, resp = _own_row(vps_id)
    if resp:
        return resp
    try:
        vps_engine.delete_container(row['container_id'])
    except Exception as exc:  # noqa: BLE001
        if 'not found' not in str(exc).lower() and 'no such container' not in str(exc).lower():
            return handle_engine(exc)
    conn = get_db()
    conn.execute('DELETE FROM vps_instances WHERE id = ?', (vps_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/user', methods=['GET'])
@auth_required
def get_user():
    conn = get_db()
    vps_count = conn.execute(
        'SELECT COUNT(*) AS count FROM vps_instances WHERE user_id = ?',
        (request.user['id'],),
    ).fetchone()
    conn.close()
    return jsonify({
        'success': True,
        'user': {
            'id': request.user['id'],
            'username': request.user['username'],
            'api_key': request.user['api_key'],
            'vps_count': vps_count['count'],
        }
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
