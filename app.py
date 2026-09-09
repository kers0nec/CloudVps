from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import random
import string
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ============ DATABASE ============
DB_PATH = 'vps.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT,
            api_key TEXT UNIQUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # VPS instances table
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
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# ============ HELPERS ============
def generate_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

def generate_api_key():
    return 'vps_' + ''.join(random.choices(string.ascii_hexdigits, k=48))

def generate_ip():
    return f"10.0.{random.randint(1, 255)}.{random.randint(1, 255)}"

def get_plans():
    return {
        'starter': {'cpu': '0.5', 'memory': '512MB', 'storage': '10GB', 'price': 'Free'},
        'standard': {'cpu': '1.0', 'memory': '1GB', 'storage': '20GB', 'price': 'Free'},
        'performance': {'cpu': '2.0', 'memory': '2GB', 'storage': '40GB', 'price': 'Free'}
    }

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ============ AUTH DECORATOR ============
def auth_required(f):
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        conn = get_db()
        user = conn.execute(
            'SELECT * FROM users WHERE api_key = ?',
            (api_key,)
        ).fetchone()
        conn.close()
        
        if not user:
            return jsonify({'error': 'Invalid API key'}), 401
        
        request.user = dict(user)
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated

# ============ PUBLIC ROUTES ============

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    user_id = generate_id()
    api_key = generate_api_key()
    
    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO users (id, username, password, api_key) VALUES (?, ?, ?, ?)',
            (user_id, username, password, api_key)
        )
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'api_key': api_key,
            'user_id': user_id,
            'username': username
        })
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Username already exists'}), 400

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    conn = get_db()
    user = conn.execute(
        'SELECT * FROM users WHERE username = ? AND password = ?',
        (username, password)
    ).fetchone()
    conn.close()
    
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    return jsonify({
        'success': True,
        'api_key': user['api_key'],
        'user_id': user['id'],
        'username': user['username']
    })

@app.route('/api/plans', methods=['GET'])
def plans():
    return jsonify(get_plans())

# ============ PROTECTED ROUTES ============

@app.route('/api/vps', methods=['POST'])
@auth_required
def create_vps():
    data = request.get_json() or {}
    plan = data.get('plan', 'starter')
    name = data.get('name', f"vps-{generate_id()[:6]}")
    
    plans = get_plans()
    if plan not in plans:
        return jsonify({'error': 'Invalid plan. Options: starter, standard, performance'}), 400
    
    config = plans[plan]
    vps_id = generate_id()
    ip = generate_ip()
    
    conn = get_db()
    conn.execute('''
        INSERT INTO vps_instances 
        (id, user_id, name, plan, cpu, memory, storage, ip) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (vps_id, request.user['id'], name, plan, config['cpu'], config['memory'], config['storage'], ip))
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'vps': {
            'id': vps_id,
            'name': name,
            'plan': plan,
            'status': 'running',
            'cpu': config['cpu'],
            'memory': config['memory'],
            'storage': config['storage'],
            'ip': ip
        }
    })

@app.route('/api/vps', methods=['GET'])
@auth_required
def list_vps():
    conn = get_db()
    vps_list = conn.execute(
        'SELECT * FROM vps_instances WHERE user_id = ? ORDER BY created_at DESC',
        (request.user['id'],)
    ).fetchall()
    conn.close()
    
    return jsonify({
        'success': True,
        'vps': [dict(row) for row in vps_list]
    })

@app.route('/api/vps/<vps_id>', methods=['GET'])
@auth_required
def get_vps(vps_id):
    conn = get_db()
    vps = conn.execute(
        'SELECT * FROM vps_instances WHERE id = ? AND user_id = ?',
        (vps_id, request.user['id'])
    ).fetchone()
    conn.close()
    
    if not vps:
        return jsonify({'error': 'VPS not found'}), 404
    
    return jsonify({'success': True, 'vps': dict(vps)})

@app.route('/api/vps/<vps_id>/start', methods=['POST'])
@auth_required
def start_vps(vps_id):
    conn = get_db()
    vps = conn.execute(
        'SELECT * FROM vps_instances WHERE id = ? AND user_id = ?',
        (vps_id, request.user['id'])
    ).fetchone()
    
    if not vps:
        conn.close()
        return jsonify({'error': 'VPS not found'}), 404
    
    conn.execute(
        'UPDATE vps_instances SET status = ? WHERE id = ?',
        ('running', vps_id)
    )
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'status': 'running'})

@app.route('/api/vps/<vps_id>/stop', methods=['POST'])
@auth_required
def stop_vps(vps_id):
    conn = get_db()
    vps = conn.execute(
        'SELECT * FROM vps_instances WHERE id = ? AND user_id = ?',
        (vps_id, request.user['id'])
    ).fetchone()
    
    if not vps:
        conn.close()
        return jsonify({'error': 'VPS not found'}), 404
    
    conn.execute(
        'UPDATE vps_instances SET status = ? WHERE id = ?',
        ('stopped', vps_id)
    )
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'status': 'stopped'})

@app.route('/api/vps/<vps_id>', methods=['DELETE'])
@auth_required
def delete_vps(vps_id):
    conn = get_db()
    vps = conn.execute(
        'SELECT * FROM vps_instances WHERE id = ? AND user_id = ?',
        (vps_id, request.user['id'])
    ).fetchone()
    
    if not vps:
        conn.close()
        return jsonify({'error': 'VPS not found'}), 404
    
    conn.execute(
        'DELETE FROM vps_instances WHERE id = ?',
        (vps_id,)
    )
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/user', methods=['GET'])
@auth_required
def get_user():
    conn = get_db()
    vps_count = conn.execute(
        'SELECT COUNT(*) as count FROM vps_instances WHERE user_id = ?',
        (request.user['id'],)
    ).fetchone()
    conn.close()
    
    return jsonify({
        'success': True,
        'user': {
            'id': request.user['id'],
            'username': request.user['username'],
            'api_key': request.user['api_key'],
            'vps_count': vps_count['count']
        }
    })

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'name': 'VPS API',
        'version': '1.0.0',
        'endpoints': {
            'public': {
                'POST /api/register': 'Create account',
                'POST /api/login': 'Get API key',
                'GET /api/plans': 'List VPS plans'
            },
            'protected (API key required)': {
                'POST /api/vps': 'Create VPS',
                'GET /api/vps': 'List all VPS',
                'GET /api/vps/<id>': 'Get VPS details',
                'POST /api/vps/<id>/start': 'Start VPS',
                'POST /api/vps/<id>/stop': 'Stop VPS',
                'DELETE /api/vps/<id>': 'Delete VPS',
                'GET /api/user': 'Get user info'
            }
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
