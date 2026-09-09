from flask import Flask, request, jsonify, send_from_directory
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
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT,
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

def auth_required(f):
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE api_key = ?', (api_key,)).fetchone()
        conn.close()
        
        if not user:
            return jsonify({'error': 'Invalid API key'}), 401
        
        request.user = dict(user)
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated

# ============ SERVE DASHBOARD ============
@app.route('/')
def index():
    return '''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Kers0ne CloudVPS</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0b0f19; color: #f9fafb; min-height: 100vh; display: flex; justify-content: center; align-items: center; }
    .container { max-width: 1200px; width: 100%; padding: 2rem; }
    .auth-card { max-width: 420px; margin: 0 auto; background: #111827; border: 1px solid #1f2937; border-radius: 16px; padding: 2.5rem; box-shadow: 0 8px 30px rgba(0,0,0,0.4); }
    .auth-card h1 { font-size: 2rem; font-weight: 700; color: #3b82f6; margin-bottom: 0.5rem; text-align: center; }
    .auth-card .subtitle { color: #9ca3af; text-align: center; margin-bottom: 2rem; }
    .form-group { margin-bottom: 1.25rem; }
    .form-group label { display: block; color: #9ca3af; font-size: 0.9rem; margin-bottom: 0.3rem; }
    .form-group input, .form-group select { width: 100%; padding: 0.75rem; border: 1px solid #1f2937; border-radius: 8px; background: #0b0f19; color: #f9fafb; font-size: 1rem; }
    .form-group input:focus, .form-group select:focus { outline: none; border-color: #3b82f6; }
    .btn { padding: 0.75rem 1.5rem; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; transition: all 0.2s; font-size: 1rem; }
    .btn-primary { background: #3b82f6; color: #fff; width: 100%; }
    .btn-primary:hover { background: #2563eb; }
    .btn-success { background: #22c55e; color: #fff; }
    .btn-success:hover { background: #16a34a; }
    .btn-danger { background: #ef4444; color: #fff; }
    .btn-danger:hover { background: #dc2626; }
    .btn-secondary { background: transparent; border: 1px solid #1f2937; color: #f9fafb; }
    .btn-secondary:hover { background: #1f2937; }
    .btn-sm { padding: 0.4rem 0.8rem; font-size: 0.8rem; }
    .toggle-link { color: #3b82f6; cursor: pointer; text-decoration: underline; }
    .toggle-link:hover { color: #2563eb; }
    .error { color: #ef4444; font-size: 0.9rem; margin-top: 0.5rem; }
    .success { color: #22c55e; font-size: 0.9rem; margin-top: 0.5rem; }
    .hidden { display: none !important; }
    .dashboard { display: none; }
    .dashboard.active { display: block; }
    .header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 1.5rem; border-bottom: 1px solid #1f2937; margin-bottom: 2rem; flex-wrap: wrap; gap: 1rem; }
    .header h1 { font-size: 1.8rem; font-weight: 700; color: #3b82f6; }
    .header .user-info { display: flex; align-items: center; gap: 1rem; }
    .header .user-info span { color: #9ca3af; }
    .header .user-info .logout { color: #ef4444; cursor: pointer; }
    .header .user-info .logout:hover { text-decoration: underline; }
    .create-card { background: #111827; border: 1px solid #1f2937; border-radius: 12px; padding: 1.5rem; margin-bottom: 2rem; }
    .create-card h2 { font-size: 1.2rem; margin-bottom: 0.5rem; }
    .create-card .subtitle { color: #9ca3af; margin-bottom: 1rem; }
    .create-card .flex-row { display: flex; gap: 1rem; flex-wrap: wrap; align-items: end; }
    .create-card .flex-row .form-group { flex: 1; min-width: 180px; margin-bottom: 0; }
    .create-card .flex-row .btn { flex-shrink: 0; }
    .vps-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem; }
    .vps-card { background: #111827; border: 1px solid #1f2937; border-radius: 12px; padding: 1.5rem; transition: transform 0.2s; }
    .vps-card:hover { transform: translateY(-4px); }
    .vps-card .name { font-size: 1.1rem; font-weight: 600; }
    .vps-card .status { display: inline-block; padding: 0.2rem 0.8rem; border-radius: 20px; font-size: 0.75rem; font-weight: 600; margin-top: 0.3rem; }
    .status-running { background: rgba(34,197,94,0.2); color: #22c55e; }
    .status-stopped { background: rgba(239,68,68,0.2); color: #ef4444; }
    .vps-card .specs { color: #9ca3af; font-size: 0.9rem; margin: 0.5rem 0; }
    .vps-card .actions { display: flex; gap: 0.5rem; margin-top: 1rem; flex-wrap: wrap; }
    .empty-state { text-align: center; color: #9ca3af; padding: 3rem 0; }
    .badge { display: inline-block; background: rgba(59,130,246,0.15); color: #3b82f6; padding: 0.15rem 0.6rem; border-radius: 12px; font-size: 0.7rem; margin-left: 0.5rem; }
    .toast { position: fixed; bottom: 2rem; right: 2rem; padding: 1rem 1.5rem; border-radius: 8px; color: #fff; font-weight: 500; z-index: 999; animation: slideIn 0.3s ease; max-width: 400px; }
    .toast-success { background: #22c55e; }
    .toast-error { background: #ef4444; }
    @keyframes slideIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
    .brand-badge { text-align: center; color: #3b82f6; font-size: 0.8rem; margin-top: 1rem; opacity: 0.5; }
    @media (max-width: 768px) { .container { padding: 1rem; } .auth-card { padding: 1.5rem; } .create-card .flex-row { flex-direction: column; } .create-card .flex-row .form-group { width: 100%; } .create-card .flex-row .btn { width: 100%; } .header { flex-direction: column; align-items: flex-start; } }
  </style>
</head>
<body>
  <div class="container">
    <!-- Auth -->
    <div id="authContainer">
      <div class="auth-card">
        <h1>🚀 Kers0ne CloudVPS</h1>
        <p class="subtitle">Free VPS hosting — powered by kers0ne</p>
        <form id="loginForm">
          <div class="form-group"><label>Username</label><input type="text" id="loginUsername" placeholder="Enter username" required></div>
          <div class="form-group"><label>Password</label><input type="password" id="loginPassword" placeholder="Enter password" required></div>
          <button type="submit" class="btn btn-primary">Login</button>
          <div id="loginError" class="error hidden"></div>
        </form>
        <form id="registerForm" class="hidden">
          <div class="form-group"><label>Username</label><input type="text" id="registerUsername" placeholder="Choose username" required></div>
          <div class="form-group"><label>Password</label><input type="password" id="registerPassword" placeholder="Choose password" required></div>
          <button type="submit" class="btn btn-primary">Create Account</button>
          <div id="registerError" class="error hidden"></div>
        </form>
        <div style="text-align:center;margin-top:1rem;color:#9ca3af;">
          <span id="toggleText">Don't have an account?</span>
          <span class="toggle-link" id="toggleAuth">Register</span>
        </div>
        <div class="brand-badge">⚡ kers0ne • free vps</div>
      </div>
    </div>

    <!-- Dashboard -->
    <div id="dashboardContainer" class="dashboard">
      <div class="header">
        <div><h1>🚀 Kers0ne CloudVPS</h1><span style="color:#9ca3af;font-size:0.9rem;">Free VPS hosting — powered by kers0ne</span></div>
        <div class="user-info">
          <span id="userDisplay">User</span>
          <span id="vpsCountBadge" class="badge">0 VPS</span>
          <span class="logout" id="logoutBtn">Logout</span>
        </div>
      </div>

      <div class="create-card">
        <h2>Create New VPS</h2>
        <p class="subtitle">Deploy a free VPS instance instantly</p>
        <div class="flex-row">
          <div class="form-group">
            <label>Plan</label>
            <select id="createPlan">
              <option value="starter">Starter (0.5 CPU, 512MB)</option>
              <option value="standard" selected>Standard (1 CPU, 1GB)</option>
              <option value="performance">Performance (2 CPU, 2GB)</option>
            </select>
          </div>
          <div class="form-group">
            <label>Name</label>
            <input type="text" id="createName" placeholder="my-vps">
          </div>
          <button class="btn btn-primary" id="createBtn">🚀 Deploy</button>
        </div>
        <div id="createError" class="error hidden"></div>
      </div>

      <h2 style="margin-bottom:1rem;">Your VPS Instances</h2>
      <div id="vpsList" class="vps-grid">
        <div class="empty-state">Loading your VPS instances...</div>
      </div>
    </div>
  </div>

  <script>
    const API_BASE = window.location.origin;
    let apiKey = localStorage.getItem('apiKey') || '';
    let currentUser = localStorage.getItem('username') || '';

    const authContainer = document.getElementById('authContainer');
    const dashboardContainer = document.getElementById('dashboardContainer');
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');
    const toggleAuth = document.getElementById('toggleAuth');
    const toggleText = document.getElementById('toggleText');
    const loginError = document.getElementById('loginError');
    const registerError = document.getElementById('registerError');
    const userDisplay = document.getElementById('userDisplay');
    const vpsCountBadge = document.getElementById('vpsCountBadge');
    const logoutBtn = document.getElementById('logoutBtn');
    const vpsList = document.getElementById('vpsList');
    const createBtn = document.getElementById('createBtn');
    const createName = document.getElementById('createName');
    const createPlan = document.getElementById('createPlan');
    const createError = document.getElementById('createError');
    let isLogin = true;

    function showToast(message, type = 'success') {
      const existing = document.querySelector('.toast');
      if (existing) existing.remove();
      const toast = document.createElement('div');
      toast.className = `toast toast-${type}`;
      toast.textContent = message;
      document.body.appendChild(toast);
      setTimeout(() => { toast.style.opacity = '0'; toast.style.transform = 'translateY(20px)'; setTimeout(() => toast.remove(), 300); }, 4000);
    }

    toggleAuth.addEventListener('click', () => {
      isLogin = !isLogin;
      loginForm.classList.toggle('hidden');
      registerForm.classList.toggle('hidden');
      toggleText.textContent = isLogin ? "Don't have an account?" : "Already have an account?";
      toggleAuth.textContent = isLogin ? 'Register' : 'Login';
      loginError.classList.add('hidden');
      registerError.classList.add('hidden');
    });

    registerForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const username = document.getElementById('registerUsername').value.trim();
      const password = document.getElementById('registerPassword').value.trim();
      if (!username || !password) { registerError.textContent = 'Username and password required'; registerError.classList.remove('hidden'); return; }
      try {
        const res = await fetch(`${API_BASE}/api/register`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) });
        const data = await res.json();
        if (data.error) { registerError.textContent = data.error; registerError.classList.remove('hidden'); return; }
        showToast('Account created! Please login.', 'success');
        registerError.classList.add('hidden');
        isLogin = true;
        loginForm.classList.remove('hidden');
        registerForm.classList.add('hidden');
        toggleText.textContent = "Don't have an account?";
        toggleAuth.textContent = 'Register';
        document.getElementById('loginUsername').value = username;
      } catch (e) { registerError.textContent = 'Network error. Try again.'; registerError.classList.remove('hidden'); }
    });

    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const username = document.getElementById('loginUsername').value.trim();
      const password = document.getElementById('loginPassword').value.trim();
      if (!username || !password) { loginError.textContent = 'Username and password required'; loginError.classList.remove('hidden'); return; }
      try {
        const res = await fetch(`${API_BASE}/api/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) });
        const data = await res.json();
        if (data.error) { loginError.textContent = data.error; loginError.classList.remove('hidden'); return; }
        apiKey = data.api_key;
        currentUser = data.username;
        localStorage.setItem('apiKey', apiKey);
        localStorage.setItem('username', currentUser);
        loginError.classList.add('hidden');
        showToast(`Welcome back, ${currentUser}!`, 'success');
        loadDashboard();
      } catch (e) { loginError.textContent = 'Network error. Try again.'; loginError.classList.remove('hidden'); }
    });

    logoutBtn.addEventListener('click', () => {
      localStorage.removeItem('apiKey');
      localStorage.removeItem('username');
      apiKey = '';
      currentUser = '';
      dashboardContainer.classList.remove('active');
      authContainer.style.display = 'block';
      showToast('Logged out.', 'success');
    });

    async function loadDashboard() {
      if (!apiKey) { authContainer.style.display = 'block'; dashboardContainer.classList.remove('active'); return; }
      authContainer.style.display = 'none';
      dashboardContainer.classList.add('active');
      userDisplay.textContent = currentUser;
      await loadVPS();
    }

    async function loadVPS() {
      vpsList.innerHTML = '<div class="empty-state">Loading your VPS instances...</div>';
      try {
        const res = await fetch(`${API_BASE}/api/vps`, { headers: { 'X-API-Key': apiKey } });
        const data = await res.json();
        if (data.error) {
          if (data.error.includes('Invalid API key')) {
            localStorage.removeItem('apiKey'); localStorage.removeItem('username'); apiKey = ''; authContainer.style.display = 'block'; dashboardContainer.classList.remove('active'); showToast('Session expired. Please login again.', 'error'); return;
          }
          vpsList.innerHTML = `<div class="empty-state">Error: ${data.error}</div>`;
          return;
        }
        const vpsArray = data.vps || [];
        vpsCountBadge.textContent = `${vpsArray.length} VPS`;
        if (vpsArray.length === 0) {
          vpsList.innerHTML = `<div class="empty-state"><p style="font-size:1.2rem;margin-bottom:0.5rem;">No VPS instances yet</p><p style="color:#6b7280;">Create your first one above! 🚀</p></div>`;
          return;
        }
        vpsList.innerHTML = vpsArray.map(vps => `
          <div class="vps-card">
            <div class="name">${escapeHtml(vps.name)}</div>
            <div><span class="status status-${vps.status}">${vps.status}</span><span class="badge">${vps.plan}</span></div>
            <div class="specs">CPU: ${vps.cpu} · Memory: ${vps.memory} · Storage: ${vps.storage}<br>IP: ${vps.ip} · ID: ${vps.id}</div>
            <div class="actions">
              ${vps.status === 'running' ? `<button class="btn btn-danger btn-sm" onclick="stopVPS('${vps.id}')">Stop</button>` : `<button class="btn btn-success btn-sm" onclick="startVPS('${vps.id}')">Start</button>`}
              <button class="btn btn-danger btn-sm" onclick="deleteVPS('${vps.id}')">Delete</button>
            </div>
          </div>
        `).join('');
      } catch (e) { vpsList.innerHTML = `<div class="empty-state">Network error. Please refresh.</div>`; }
    }

    createBtn.addEventListener('click', async () => {
      const name = createName.value.trim() || `vps-${Date.now().toString(36)}`;
      const plan = createPlan.value;
      createBtn.textContent = 'Deploying...';
      createBtn.disabled = true;
      createError.classList.add('hidden');
      try {
        const res = await fetch(`${API_BASE}/api/vps`, { method: 'POST', headers: { 'X-API-Key': apiKey, 'Content-Type': 'application/json' }, body: JSON.stringify({ name, plan }) });
        const data = await res.json();
        if (data.error) { createError.textContent = data.error; createError.classList.remove('hidden'); return; }
        createName.value = '';
        showToast(`VPS "${data.vps.name}" created successfully! 🚀`, 'success');
        loadVPS();
      } catch (e) { createError.textContent = 'Network error. Try again.'; createError.classList.remove('hidden'); }
      finally { createBtn.textContent = '🚀 Deploy'; createBtn.disabled = false; }
    });

    async function startVPS(id) { try { await fetch(`${API_BASE}/api/vps/${id}/start`, { method: 'POST', headers: { 'X-API-Key': apiKey } }); showToast('VPS starting...', 'success'); loadVPS(); } catch (e) { showToast('Error starting VPS', 'error'); } }
    async function stopVPS(id) { try { await fetch(`${API_BASE}/api/vps/${id}/stop`, { method: 'POST', headers: { 'X-API-Key': apiKey } }); showToast('VPS stopping...', 'success'); loadVPS(); } catch (e) { showToast('Error stopping VPS', 'error'); } }
    async function deleteVPS(id) { if (!confirm('Delete this VPS permanently?')) return; try { await fetch(`${API_BASE}/api/vps/${id}`, { method: 'DELETE', headers: { 'X-API-Key': apiKey } }); showToast('VPS deleted.', 'success'); loadVPS(); } catch (e) { showToast('Error deleting VPS', 'error'); } }

    function escapeHtml(str) { const div = document.createElement('div'); div.textContent = str; return div.innerHTML; }

    if (apiKey && currentUser) { loadDashboard(); } else { authContainer.style.display = 'block'; dashboardContainer.classList.remove('active'); }
    setInterval(() => { if (dashboardContainer.classList.contains('active')) { loadVPS(); } }, 30000);
  </script>
</body>
</html>
    '''

# ============ API ROUTES ============
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
            'username': username,
            'brand': 'kers0ne'
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
        'username': user['username'],
        'brand': 'kers0ne'
    })

@app.route('/api/plans', methods=['GET'])
def plans():
    return jsonify(get_plans())

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
        'brand': 'kers0ne',
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
        'brand': 'kers0ne',
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
    
    return jsonify({
        'success': True,
        'brand': 'kers0ne',
        'vps': dict(vps)
    })

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
    
    conn.execute('UPDATE vps_instances SET status = ? WHERE id = ?', ('running', vps_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'brand': 'kers0ne', 'status': 'running'})

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
    
    conn.execute('UPDATE vps_instances SET status = ? WHERE id = ?', ('stopped', vps_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'brand': 'kers0ne', 'status': 'stopped'})

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
    
    conn.execute('DELETE FROM vps_instances WHERE id = ?', (vps_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'brand': 'kers0ne'})

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
        'brand': 'kers0ne',
        'user': {
            'id': request.user['id'],
            'username': request.user['username'],
            'api_key': request.user['api_key'],
            'vps_count': vps_count['count']
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
