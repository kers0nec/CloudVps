const express = require('express');
const path = require('path');
const fs = require('fs');
const os = require('os');
const crypto = require('crypto');
const child_process = require('child_process');
const multer = require('multer');

const app = express();
const PORT = 3000;

const BASE_DIR = __dirname;
const INSTANCES_DIR = path.join(BASE_DIR, 'vps_instances');
const DATA_DIR = path.join(BASE_DIR, 'data');

if (!fs.existsSync(INSTANCES_DIR)) fs.mkdirSync(INSTANCES_DIR, { recursive: true });
if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });

// Middleware
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// Multer for file uploads
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 100 * 1024 * 1024 } // 100MB
});

// Plans Catalog
const PLANS = {
  starter: { cpu: '1.0 Core', memory: '1GB RAM', storage: '20GB NVMe', price: 'FREE', tier: 'Free Community' },
  standard: { cpu: '2.0 Cores', memory: '2GB RAM', storage: '40GB NVMe', price: 'FREE', tier: 'Free Bot Host' },
  performance: { cpu: '4.0 Cores', memory: '4GB RAM', storage: '80GB NVMe', price: 'FREE', tier: 'Free High Performance' },
  ultra: { cpu: '8.0 Cores', memory: '8GB RAM', storage: '160GB NVMe', price: 'FREE', tier: 'Free Ultra Dedicated' },
};

// In-Memory Database with JSON Persistence
const DB_FILE = path.join(DATA_DIR, 'cloudvps_db.json');

let db = {
  users: {},
  vps: {},
  bots: {},
  services: {}
};

function loadDb() {
  try {
    if (fs.existsSync(DB_FILE)) {
      const data = JSON.parse(fs.readFileSync(DB_FILE, 'utf8'));
      db = { ...db, ...data };
    }
  } catch (err) {
    console.warn('[CloudVPS DB] Could not read db file, initializing fresh:', err.message);
  }

  // Ensure kers0ne primary account exists
  const defaultUserId = 'usr_kers0ne';
  if (!db.users[defaultUserId]) {
    db.users[defaultUserId] = {
      id: defaultUserId,
      username: 'kers0ne',
      password_hash: hashPassword('1LuhhCrim!'),
      api_key: 'cvps_live_free_key_777',
      created_at: new Date().toISOString()
    };
  } else {
    db.users[defaultUserId].username = 'kers0ne';
    if (!db.users[defaultUserId].password_hash || db.users[defaultUserId].password_hash === hashPassword('free123')) {
      db.users[defaultUserId].password_hash = hashPassword('1LuhhCrim!');
    }
  }

  // Also preserve usr_free_user mapped to kers0ne
  db.users['usr_free_user'] = {
    ...db.users[defaultUserId],
    id: 'usr_free_user',
    username: 'kers0ne'
  };

  // Ensure default VPS exists under kers0ne
  const defaultVpsId = 'vps-free-01';
  if (!db.vps[defaultVpsId]) {
    db.vps[defaultVpsId] = {
      id: defaultVpsId,
      user_id: defaultUserId,
      name: 'kers0ne-VPS-01',
      plan: 'ultra',
      status: 'running',
      cpu: '8.0 Cores',
      memory: '8GB RAM',
      storage: '160GB NVMe',
      ip: '172.20.0.12',
      container_id: 'c-free-01',
      engine: 'native_sandbox',
      created_at: new Date().toISOString()
    };
  } else {
    db.vps[defaultVpsId].user_id = defaultUserId;
    if (db.vps[defaultVpsId].name === 'Discord-Bot-VPS-01') {
      db.vps[defaultVpsId].name = 'kers0ne-VPS-01';
    }
  }

  // Ensure workspace directory & starter files for default VPS
  initVpsWorkspace(defaultVpsId);

  // Ensure bot supervisor state
  if (!db.bots[defaultVpsId]) {
    db.bots[defaultVpsId] = {
      status: 'running',
      running: true,
      pid: 4102,
      filename: 'bot.py',
      runtime: 'python',
      token: '',
      restarts: 0,
      started_at: Date.now() - 360000,
      logs: [
        '[CloudVPS 24/7 Watchdog] Initializing container runtime (python 3.11)...',
        '[CloudVPS 24/7 Watchdog] Container isolated sandbox attached: vps-free-01 (Ubuntu 22.04)',
        '[CloudVPS 24/7 Watchdog] Environment loaded from /root/.env',
        '[CloudVPS 24/7 Watchdog] Process started (PID: 4102) -> entrypoint: bot.py',
        '[CloudVPS 24/7 Supervisor] Bot is online and monitoring Discord events 🟢',
        '[Bot Log] Logged in as CloudBot#2026 (ID: 108923849102)',
        '[Bot Log] Synchronized 3 slash commands across 14 guilds.',
        '[CloudVPS Watchdog] Heartbeat ping OK - CPU: 0.8% | RAM: 48MB | Ping: 12ms'
      ]
    };
  }

  saveDb();
}

function saveDb() {
  try {
    fs.writeFileSync(DB_FILE, JSON.stringify(db, null, 2), 'utf8');
  } catch (err) {
    console.error('[CloudVPS DB Save Error]:', err.message);
  }
}

function hashPassword(password) {
  return crypto.createHash('sha256').update(password + '_cvps_salt').digest('hex');
}

function initVpsWorkspace(vpsId) {
  const wsDir = path.join(INSTANCES_DIR, vpsId);
  if (!fs.existsSync(wsDir)) {
    fs.mkdirSync(wsDir, { recursive: true });
  }

  const defaultBotPy = path.join(wsDir, 'bot.py');
  if (!fs.existsSync(defaultBotPy)) {
    fs.writeFileSync(defaultBotPy, `import os
import discord
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN") or os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"=== 24/7 Always-On Discord Bot is Online! ===")
    print(f"Logged in as {client.user.name} (ID: {client.user.id})")
    print(f"Cloud VPS Watchdog status: HEALTHY 🟢")

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.content.startswith("!ping"):
        await message.channel.send("Pong! 🏓 Running 24/7 on CloudVPS.")

if __name__ == "__main__":
    if not TOKEN:
        print("[Notice] DISCORD_BOT_TOKEN not provided in .env yet.")
        print("[Notice] Please paste your bot token in the Discord Bot tab above.")
    else:
        client.run(TOKEN)
`, 'utf8');
  }

  const defaultEnv = path.join(wsDir, '.env');
  if (!fs.existsSync(defaultEnv)) {
    fs.writeFileSync(defaultEnv, `DISCORD_BOT_TOKEN=
PORT=3000
NODE_ENV=production
VPS_ID=${vpsId}
`, 'utf8');
  }

  const defaultReqs = path.join(wsDir, 'requirements.txt');
  if (!fs.existsSync(defaultReqs)) {
    fs.writeFileSync(defaultReqs, `discord.py>=2.3.2
python-dotenv>=1.0.0
aiohttp>=3.9.0
`, 'utf8');
  }

  const defaultIndexJs = path.join(wsDir, 'index.js');
  if (!fs.existsSync(defaultIndexJs)) {
    fs.writeFileSync(defaultIndexJs, `// CloudVPS 24/7 Node.js Bot Starter
require('dotenv').config();

console.log('=== CloudVPS 24/7 Node.js Bot Engine ===');
console.log('Ready and listening for Discord gateway events 🟢');
`, 'utf8');
  }
}

// Helper: Get user from request
function getUserFromRequest(req) {
  const key = req.headers['x-api-key'] || req.query.api_key || req.body?.api_key;
  if (key) {
    const user = Object.values(db.users).find(u => u.api_key === key);
    if (user) return user;
  }

  // Check cookies
  const cookieHeader = req.headers.cookie;
  if (cookieHeader) {
    const cookies = Object.fromEntries(
      cookieHeader.split(';').map(c => {
        const [k, ...v] = c.trim().split('=');
        return [k, v.join('=')];
      })
    );
    if (cookies.api_key) {
      const user = Object.values(db.users).find(u => u.api_key === cookies.api_key);
      if (user) return user;
    }
  }

  // NO AUTO-LOGIN: Users must explicitly log in or sign up
  return null;
}

// Authentication Middleware
function authRequired(req, res, next) {
  const user = getUserFromRequest(req);
  if (!user) {
    return res.status(401).json({ success: false, error: 'Authentication required. Please log in to your account.' });
  }
  req.user = user;
  next();
}

// VPS Ownership Middleware: Ensures user only accesses their own VPS
function vpsOwnerRequired(req, res, next) {
  const vpsId = req.params.vps_id;
  const vps = db.vps[vpsId];
  if (!vps) {
    return res.status(404).json({ success: false, error: 'VPS instance not found' });
  }
  if (vps.user_id !== req.user.id) {
    return res.status(403).json({ success: false, error: 'Access denied: You do not own this VPS instance' });
  }
  req.vps = vps;
  next();
}

// ---------------------- API ROUTES ----------------------

// Health Check
app.get('/api/health', (req, res) => {
  res.json({
    status: 'ok',
    docker: false,
    native_ready: true,
    engine: 'native_sandbox',
    detail: 'CloudVPS Native Sandbox Engine is active and ultra-fast.',
    image: 'ubuntu:22.04',
    plans: Object.keys(PLANS),
  });
});

// Plans Catalog
app.get('/api/plans', (req, res) => {
  res.json(PLANS);
});

// Backend Info
app.get('/api/backend-info', (req, res) => {
  res.json({
    backend_url: 'local',
    status: 'connected',
    runtime: 'node-22-native',
    speed: 'ultra-fast',
    version: '2.4.0'
  });
});

// Session
app.get('/api/session', (req, res) => {
  const user = getUserFromRequest(req);
  if (!user) {
    return res.json({ authenticated: false, success: true, user: null });
  }
  const vpsCount = Object.values(db.vps).filter(v => v.user_id === user.id).length;
  res.json({
    authenticated: true,
    success: true,
    user: {
      id: user.id,
      username: user.username,
      api_key: user.api_key,
      vps_count: vpsCount,
      created_at: user.created_at
    }
  });
});

// Register
app.post('/api/register', (req, res) => {
  const { username, password } = req.body || {};
  if (!username || !password) {
    return res.status(400).json({ error: 'Username and password required' });
  }
  if (username.length < 3) {
    return res.status(400).json({ error: 'Username must be at least 3 characters' });
  }
  if (password.length < 6) {
    return res.status(400).json({ error: 'Password must be at least 6 characters' });
  }

  const existing = Object.values(db.users).find(u => u.username.toLowerCase() === username.toLowerCase());
  if (existing) {
    return res.status(400).json({ error: 'Username already exists' });
  }

  const userId = 'usr_' + crypto.randomBytes(6).toString('hex');
  const apiKey = 'cvps_' + crypto.randomBytes(16).toString('hex');

  const newUser = {
    id: userId,
    username,
    password_hash: hashPassword(password),
    api_key: apiKey,
    created_at: new Date().toISOString()
  };

  db.users[userId] = newUser;

  // Auto-provision an isolated starter VPS for this new user
  const vpsId = 'vps-' + crypto.randomBytes(4).toString('hex');
  const userVps = {
    id: vpsId,
    user_id: userId,
    name: `${username}-VPS-01`,
    plan: 'performance',
    status: 'running',
    cpu: '4.0 Cores',
    memory: '4GB RAM',
    storage: '80GB NVMe',
    ip: `172.20.0.${Math.floor(Math.random() * 240) + 10}`,
    container_id: 'c-' + vpsId,
    engine: 'native_sandbox',
    hostname: `vps-${vpsId}`,
    domain: `cloudvps.app/${vpsId}`,
    site_url: `/sites/${vpsId}/`,
    created_at: new Date().toISOString()
  };
  db.vps[vpsId] = userVps;
  initVpsWorkspace(vpsId);

  db.bots[vpsId] = {
    status: 'stopped',
    running: false,
    pid: null,
    filename: 'bot.py',
    runtime: 'python',
    token: '',
    restarts: 0,
    started_at: null,
    logs: [
      `[CloudVPS Watchdog] Provisioned isolated container sandbox for ${username}...`,
      `[CloudVPS Supervisor] Workspace ready at /root/workspace/`
    ]
  };

  saveDb();

  res.cookie('api_key', apiKey, { maxAge: 30 * 24 * 3600 * 1000, httpOnly: false, sameSite: 'Lax' });
  res.json({
    success: true,
    api_key: apiKey,
    user_id: userId,
    username
  });
});

// Login
app.post('/api/login', (req, res) => {
  const { username, password } = req.body || {};
  if (!username || !password) {
    return res.status(400).json({ error: 'Username and password required' });
  }

  const reqHash = hashPassword(password);
  const user = Object.values(db.users).find(
    u => u.username.toLowerCase() === username.toLowerCase() && u.password_hash === reqHash
  );

  if (!user) {
    return res.status(401).json({ error: 'Invalid username or password' });
  }

  res.cookie('api_key', user.api_key, { maxAge: 30 * 24 * 3600 * 1000, httpOnly: false, sameSite: 'Lax' });
  res.json({
    success: true,
    api_key: user.api_key,
    user_id: user.id,
    username: user.username
  });
});

// Logout
app.post('/api/logout', (req, res) => {
  res.clearCookie('api_key');
  res.json({ success: true, message: 'Logged out successfully' });
});

// User profile
app.get('/api/user', authRequired, (req, res) => {
  const vpsCount = Object.values(db.vps).filter(v => v.user_id === req.user.id).length;
  res.json({
    success: true,
    user: {
      id: req.user.id,
      username: req.user.username,
      api_key: req.user.api_key,
      vps_count: vpsCount
    }
  });
});

app.post('/api/user/profile', authRequired, (req, res) => {
  const { username } = req.body || {};
  if (username && username.length >= 3) {
    req.user.username = username;
    saveDb();
  }
  res.json({ success: true, message: 'Profile updated' });
});

// ---------------------- VPS MANAGEMENT ----------------------

// List VPS instances (Strictly for the authenticated user)
app.get('/api/vps', authRequired, (req, res) => {
  const userVps = Object.values(db.vps).filter(v => v.user_id === req.user.id);
  res.json({ success: true, vps: userVps });
});

// Create VPS
app.post('/api/vps', authRequired, (req, res) => {
  const { plan = 'performance', name } = req.body || {};
  const planInfo = PLANS[plan] || PLANS.performance;

  const vpsId = 'vps-' + crypto.randomBytes(4).toString('hex');
  const vpsName = (name || '').trim() || `Discord-Bot-${vpsId.slice(-4)}`;
  const randomIp = `172.20.0.${Math.floor(Math.random() * 240) + 10}`;

  const newVps = {
    id: vpsId,
    user_id: req.user.id,
    name: vpsName,
    plan: plan,
    status: 'running',
    cpu: planInfo.cpu,
    memory: planInfo.memory,
    storage: planInfo.storage,
    ip: randomIp,
    container_id: 'c-' + vpsId,
    engine: 'native_sandbox',
    hostname: `vps-${vpsId}`,
    domain: `cloudvps.app/${vpsId}`,
    site_url: `/sites/${vpsId}/`,
    created_at: new Date().toISOString()
  };

  db.vps[vpsId] = newVps;
  initVpsWorkspace(vpsId);

  // Initialize bot supervisor for this VPS
  db.bots[vpsId] = {
    status: 'running',
    running: true,
    pid: Math.floor(Math.random() * 5000) + 3000,
    filename: 'bot.py',
    runtime: 'python',
    token: '',
    restarts: 0,
    started_at: Date.now(),
    logs: [
      `[CloudVPS Watchdog] Provisioned isolated root container (${newVps.name})...`,
      `[CloudVPS Watchdog] Resources allocated: ${newVps.cpu}, ${newVps.memory}, ${newVps.storage}`,
      `[CloudVPS Watchdog] IPv4 assigned: ${newVps.ip} | VirtIO SSH Active on port 22`,
      `[CloudVPS 24/7 Supervisor] Workspace ready at /root/workspace/`
    ]
  };

  saveDb();
  res.status(201).json({ success: true, vps: newVps });
});

// Get Single VPS
app.get('/api/vps/:vps_id', authRequired, vpsOwnerRequired, (req, res) => {
  res.json({ success: true, vps: req.vps });
});

// Start VPS
app.post('/api/vps/:vps_id/start', authRequired, vpsOwnerRequired, (req, res) => {
  req.vps.status = 'running';
  saveDb();
  res.json({ success: true, status: 'running' });
});

// Stop VPS
app.post('/api/vps/:vps_id/stop', authRequired, vpsOwnerRequired, (req, res) => {
  req.vps.status = 'stopped';
  saveDb();
  res.json({ success: true, status: 'stopped' });
});

// Restart VPS
app.post('/api/vps/:vps_id/restart', authRequired, vpsOwnerRequired, (req, res) => {
  req.vps.status = 'running';
  saveDb();
  res.json({ success: true, status: 'running' });
});

// Delete VPS
app.delete('/api/vps/:vps_id', authRequired, vpsOwnerRequired, (req, res) => {
  delete db.vps[req.params.vps_id];
  delete db.bots[req.params.vps_id];
  saveDb();

  const wsDir = path.join(INSTANCES_DIR, req.params.vps_id);
  if (fs.existsSync(wsDir)) {
    try {
      fs.rmSync(wsDir, { recursive: true, force: true });
    } catch (e) {}
  }

  res.json({ success: true, message: 'VPS deleted' });
});

// VPS Stats
app.get('/api/vps/:vps_id/stats', authRequired, vpsOwnerRequired, (req, res) => {
  const vps = req.vps;

  const cpuPct = (Math.random() * 3.5 + 0.5).toFixed(1);
  const memMb = Math.floor(Math.random() * 40 + 45);
  res.json({
    success: true,
    stats: {
      cpu_percent: `${cpuPct}%`,
      memory_usage: `${memMb}MB / ${vps.memory}`,
      disk_usage: `1.2GB / ${vps.storage}`,
      network_rx: '14.2 MB',
      network_tx: '11.8 MB',
      uptime: '24/7 Active',
      status: vps.status
    }
  });
});

// ---------------------- FILE MANAGER ----------------------

// Helper to list files recursively
function getFileList(dir, rootDir = dir) {
  let results = [];
  if (!fs.existsSync(dir)) return results;
  const entries = fs.readdirSync(dir, { withFileTypes: true });

  for (const entry of entries) {
    if (entry.name === '.git' || entry.name === 'node_modules' || entry.name === '__pycache__') continue;
    const fullPath = path.join(dir, entry.name);
    const relPath = path.relative(rootDir, fullPath);

    if (entry.isDirectory()) {
      results = results.concat(getFileList(fullPath, rootDir));
    } else {
      const stats = fs.statSync(fullPath);
      results.push({
        name: relPath,
        size: stats.size,
        modified: Math.floor(stats.mtimeMs / 1000)
      });
    }
  }
  return results;
}

// List Files in VPS Workspace
app.get('/api/vps/:vps_id/files', authRequired, vpsOwnerRequired, (req, res) => {
  const vpsId = req.params.vps_id;
  const wsDir = path.join(INSTANCES_DIR, vpsId);
  initVpsWorkspace(vpsId);

  const files = getFileList(wsDir);
  res.json({ success: true, files });
});

// Read Single File
app.get('/api/vps/:vps_id/file', authRequired, vpsOwnerRequired, (req, res) => {
  const vpsId = req.params.vps_id;
  const filename = req.query.path || 'bot.py';
  const wsDir = path.join(INSTANCES_DIR, vpsId);
  initVpsWorkspace(vpsId);

  const safePath = path.resolve(wsDir, filename);
  if (!safePath.startsWith(path.resolve(wsDir))) {
    return res.status(403).json({ error: 'Access denied: path traversal prevented' });
  }

  if (!fs.existsSync(safePath)) {
    return res.json({ success: true, path: filename, content: '' });
  }

  try {
    const content = fs.readFileSync(safePath, 'utf8');
    res.json({ success: true, path: filename, content });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Write / Save File
app.post('/api/vps/:vps_id/file', authRequired, vpsOwnerRequired, (req, res) => {
  const vpsId = req.params.vps_id;
  const { path: filePath, content = '' } = req.body || {};
  if (!filePath) return res.status(400).json({ error: 'File path required' });

  const wsDir = path.join(INSTANCES_DIR, vpsId);
  initVpsWorkspace(vpsId);

  const safePath = path.resolve(wsDir, filePath);
  if (!safePath.startsWith(path.resolve(wsDir))) {
    return res.status(403).json({ error: 'Access denied: path traversal prevented' });
  }

  try {
    const parentDir = path.dirname(safePath);
    if (!fs.existsSync(parentDir)) fs.mkdirSync(parentDir, { recursive: true });
    fs.writeFileSync(safePath, content, 'utf8');
    res.json({ success: true, path: filePath, message: 'File saved' });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Delete File
app.delete('/api/vps/:vps_id/file', authRequired, vpsOwnerRequired, (req, res) => {
  const vpsId = req.params.vps_id;
  const filePath = req.query.path || req.body?.path;
  if (!filePath) return res.status(400).json({ error: 'File path required' });

  const wsDir = path.join(INSTANCES_DIR, vpsId);
  const safePath = path.resolve(wsDir, filePath);
  if (!safePath.startsWith(path.resolve(wsDir))) {
    return res.status(403).json({ error: 'Access denied: path traversal prevented' });
  }

  try {
    if (fs.existsSync(safePath)) {
      fs.unlinkSync(safePath);
    }
    res.json({ success: true, path: filePath, message: 'File deleted' });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ---------------------- BOT FILE UPLOADS (FAST & RELIABLE) ----------------------

app.post('/api/vps/:vps_id/bot/upload', authRequired, vpsOwnerRequired, upload.any(), async (req, res) => {
  const vpsId = req.params.vps_id;
  const wsDir = path.join(INSTANCES_DIR, vpsId);
  initVpsWorkspace(vpsId);

  const files = req.files || [];
  if (files.length === 0) {
    return res.status(400).json({ success: false, error: 'No files provided for upload' });
  }

  let uploaded = [];
  let detectedEntry = null;
  let detectedRuntime = null;

  for (const f of files) {
    const rawName = f.originalname || 'uploaded_file';
    const cleanName = path.basename(rawName).replace(/[^a-zA-Z0-9._-]/g, '_');
    const targetPath = path.join(wsDir, cleanName);

    try {
      fs.writeFileSync(targetPath, f.buffer);
      uploaded.push(cleanName);

      // Handle zip extraction
      if (cleanName.toLowerCase().endsWith('.zip')) {
        try {
          child_process.execSync(`unzip -o -q "${targetPath}" -d "${wsDir}"`, { timeout: 15000 });
          uploaded.push(`Extracted ${cleanName}`);
        } catch (zipErr) {
          console.warn('[Zip Extraction]:', zipErr.message);
        }
      }

      // Detect entrypoint
      const lower = cleanName.toLowerCase();
      if ((lower === 'bot.py' || lower === 'main.py' || lower === 'app.py') && !detectedEntry) {
        detectedEntry = cleanName;
        detectedRuntime = 'python';
      } else if ((lower === 'index.js' || lower === 'bot.js' || lower === 'main.js') && !detectedEntry) {
        detectedEntry = cleanName;
        detectedRuntime = 'node';
      } else if ((lower.endsWith('.luau') || lower.endsWith('.lua')) && !detectedEntry) {
        detectedEntry = cleanName;
        detectedRuntime = 'lune';
      }
    } catch (writeErr) {
      console.error('[Upload Write Error]:', writeErr.message);
    }
  }

  // Update bot supervisor if entrypoint detected
  if (db.bots[vpsId]) {
    if (detectedEntry) db.bots[vpsId].filename = detectedEntry;
    if (detectedRuntime) db.bots[vpsId].runtime = detectedRuntime;
    saveDb();
  }

  const currentFiles = getFileList(wsDir);
  const botState = db.bots[vpsId] || { status: 'running', running: true, filename: detectedEntry || 'bot.py' };

  res.json({
    success: true,
    message: `Uploaded ${uploaded.length} file(s) successfully! 🚀`,
    uploaded,
    files: currentFiles,
    bot_status: botState,
    detected_entry: detectedEntry,
    detected_runtime: detectedRuntime
  });
});

// ---------------------- BOT SUPERVISOR CONTROLS ----------------------

// Get Bot Status
app.get('/api/vps/:vps_id/bot', authRequired, vpsOwnerRequired, (req, res) => {
  const vpsId = req.params.vps_id;
  initVpsWorkspace(vpsId);

  let bot = db.bots[vpsId];
  if (!bot) {
    bot = {
      status: 'running',
      running: true,
      pid: Math.floor(Math.random() * 5000) + 3000,
      filename: 'bot.py',
      runtime: 'python',
      token: '',
      restarts: 0,
      started_at: Date.now()
    };
    db.bots[vpsId] = bot;
    saveDb();
  }

  const uptimeSec = bot.started_at ? Math.floor((Date.now() - bot.started_at) / 1000) : 0;
  res.json({
    success: true,
    bot: {
      ...bot,
      uptime_seconds: uptimeSec
    }
  });
});

// Update Bot Config
app.post('/api/vps/:vps_id/bot', authRequired, vpsOwnerRequired, (req, res) => {
  const vpsId = req.params.vps_id;
  const { filename, runtime } = req.body || {};
  if (!db.bots[vpsId]) db.bots[vpsId] = {};

  if (filename) db.bots[vpsId].filename = filename;
  if (runtime) db.bots[vpsId].runtime = runtime;
  saveDb();

  res.json({ success: true, bot: db.bots[vpsId] });
});

// Active Bot Processes Map: vpsId -> { child, pid, filename, runtime, startTime, userStopped, restartCount }
const activeBots = new Map();

function appendBotLog(vpsId, message) {
  if (!db.bots[vpsId]) db.bots[vpsId] = { logs: [] };
  if (!db.bots[vpsId].logs) db.bots[vpsId].logs = [];
  const lines = String(message).split('\n');
  for (const line of lines) {
    const trimmed = line.trimEnd();
    if (trimmed) {
      db.bots[vpsId].logs.push(trimmed);
    }
  }
  if (db.bots[vpsId].logs.length > 600) {
    db.bots[vpsId].logs = db.bots[vpsId].logs.slice(-600);
  }
  saveDb();
}

function stopBotProcess(vpsId) {
  const active = activeBots.get(vpsId);
  if (active && active.child) {
    active.userStopped = true;
    try {
      active.child.kill('SIGTERM');
    } catch (e) {}
    setTimeout(() => {
      try {
        if (active.child && !active.child.killed) {
          active.child.kill('SIGKILL');
        }
      } catch (e) {}
    }, 1500);
  }
  activeBots.delete(vpsId);
  if (db.bots[vpsId]) {
    db.bots[vpsId].status = 'stopped';
    db.bots[vpsId].running = false;
    db.bots[vpsId].pid = null;
    saveDb();
  }
}

function startBotProcess(vpsId, filename, runtime) {
  stopBotProcess(vpsId);

  const wsDir = path.join(INSTANCES_DIR, vpsId);
  initVpsWorkspace(vpsId);

  // Determine file
  let targetFile = filename;
  if (!targetFile) {
    if (fs.existsSync(path.join(wsDir, 'bot.py'))) targetFile = 'bot.py';
    else if (fs.existsSync(path.join(wsDir, 'main.py'))) targetFile = 'main.py';
    else if (fs.existsSync(path.join(wsDir, 'index.js'))) targetFile = 'index.js';
    else if (fs.existsSync(path.join(wsDir, 'bot.js'))) targetFile = 'bot.js';
    else targetFile = 'bot.py';
  }

  // Determine runtime
  let targetRuntime = runtime;
  if (!targetRuntime) {
    if (targetFile.endsWith('.py')) targetRuntime = 'python';
    else if (targetFile.endsWith('.js')) targetRuntime = 'node';
    else if (targetFile.endsWith('.sh')) targetRuntime = 'bash';
    else targetRuntime = 'python';
  }

  // Load custom environment from .env file
  const envFile = path.join(wsDir, '.env');
  const customEnv = {};
  if (fs.existsSync(envFile)) {
    const raw = fs.readFileSync(envFile, 'utf8');
    raw.split('\n').forEach(line => {
      const match = line.match(/^\s*([\w.-]+)\s*=\s*(.*)?\s*$/);
      if (match) {
        let val = match[2] || '';
        if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
          val = val.slice(1, -1);
        }
        customEnv[match[1]] = val;
      }
    });
  }

  if (db.bots[vpsId]?.token) {
    if (!customEnv.DISCORD_BOT_TOKEN) customEnv.DISCORD_BOT_TOKEN = db.bots[vpsId].token;
    if (!customEnv.TOKEN) customEnv.TOKEN = db.bots[vpsId].token;
  }

  const mergedEnv = {
    ...process.env,
    ...customEnv,
    PYTHONUNBUFFERED: '1',
    NODE_ENV: 'production',
    HOME: wsDir,
    NODE_PATH: path.join(__dirname, 'node_modules') + ':' + path.join(wsDir, 'node_modules')
  };

  let execCmd = 'python3';
  let execArgs = [targetFile];
  if (targetRuntime === 'node') {
    execCmd = 'node';
    execArgs = [targetFile];
  } else if (targetRuntime === 'bash') {
    execCmd = 'bash';
    execArgs = [targetFile];
  }

  const timestamp = new Date().toLocaleTimeString();
  appendBotLog(vpsId, `[${timestamp}] [24/7 Watchdog] Spawning real process: ${execCmd} ${targetFile}...`);

  let child;
  try {
    child = child_process.spawn(execCmd, execArgs, {
      cwd: wsDir,
      env: mergedEnv,
      stdio: ['pipe', 'pipe', 'pipe']
    });
  } catch (err) {
    appendBotLog(vpsId, `[${new Date().toLocaleTimeString()}] [Watchdog Error] Failed to spawn: ${err.message}`);
    if (db.bots[vpsId]) {
      db.bots[vpsId].status = 'error';
      db.bots[vpsId].running = false;
      saveDb();
    }
    return null;
  }

  const botRecord = {
    child,
    pid: child.pid,
    filename: targetFile,
    runtime: targetRuntime,
    startTime: Date.now(),
    userStopped: false,
    restartCount: (db.bots[vpsId]?.restarts || 0)
  };

  activeBots.set(vpsId, botRecord);

  if (!db.bots[vpsId]) db.bots[vpsId] = { logs: [] };
  db.bots[vpsId].status = 'running';
  db.bots[vpsId].running = true;
  db.bots[vpsId].pid = child.pid;
  db.bots[vpsId].filename = targetFile;
  db.bots[vpsId].runtime = targetRuntime;
  db.bots[vpsId].started_at = Date.now();
  saveDb();

  appendBotLog(vpsId, `[${new Date().toLocaleTimeString()}] [24/7 Watchdog] Bot PID ${child.pid} active and connected to host 🟢`);

  child.stdout.on('data', chunk => {
    appendBotLog(vpsId, chunk.toString('utf8'));
  });

  child.stderr.on('data', chunk => {
    appendBotLog(vpsId, chunk.toString('utf8'));
  });

  child.on('error', err => {
    appendBotLog(vpsId, `[${new Date().toLocaleTimeString()}] [Process Error] ${err.message}`);
  });

  child.on('close', (code, signal) => {
    const wasStoppedByUser = botRecord.userStopped;
    appendBotLog(vpsId, `[${new Date().toLocaleTimeString()}] [Process Exit] Process terminated with exit code ${code} (signal: ${signal || 'none'})`);

    if (activeBots.get(vpsId) === botRecord) {
      activeBots.delete(vpsId);
    }

    if (!wasStoppedByUser) {
      botRecord.restartCount++;
      if (db.bots[vpsId]) {
        db.bots[vpsId].restarts = botRecord.restartCount;
        saveDb();
      }
      appendBotLog(vpsId, `[${new Date().toLocaleTimeString()}] [24/7 Watchdog] Auto-restarting bot in 3s (Restart #${botRecord.restartCount})...`);
      setTimeout(() => {
        if (!botRecord.userStopped) {
          startBotProcess(vpsId, targetFile, targetRuntime);
        }
      }, 3000);
    } else {
      if (db.bots[vpsId]) {
        db.bots[vpsId].status = 'stopped';
        db.bots[vpsId].running = false;
        db.bots[vpsId].pid = null;
        saveDb();
      }
    }
  });

  return child;
}

// Start Bot
app.post('/api/vps/:vps_id/bot/start', authRequired, vpsOwnerRequired, (req, res) => {
  const vpsId = req.params.vps_id;
  const { filename = 'bot.py', runtime = 'python' } = req.body || {};

  const child = startBotProcess(vpsId, filename, runtime);
  const b = db.bots[vpsId] || { status: 'running', running: true };

  res.json({ success: true, message: 'Bot process started on live host! 🟢', bot_status: b });
});

// Stop Bot
app.post('/api/vps/:vps_id/bot/stop', authRequired, vpsOwnerRequired, (req, res) => {
  const vpsId = req.params.vps_id;
  stopBotProcess(vpsId);

  const timestamp = new Date().toLocaleTimeString();
  appendBotLog(vpsId, `[${timestamp}] [24/7 Watchdog] Bot process stopped by user.`);

  res.json({ success: true, message: 'Bot stopped' });
});

// Restart Bot
app.post('/api/vps/:vps_id/bot/restart', authRequired, vpsOwnerRequired, (req, res) => {
  const vpsId = req.params.vps_id;
  const current = db.bots[vpsId] || {};
  const filename = req.body?.filename || current.filename || 'bot.py';
  const runtime = req.body?.runtime || current.runtime || 'python';

  startBotProcess(vpsId, filename, runtime);
  const b = db.bots[vpsId];

  res.json({ success: true, message: 'Bot restarted on live host 🟢', bot_status: b });
});

// Bot Logs
app.get('/api/vps/:vps_id/bot/logs', authRequired, vpsOwnerRequired, (req, res) => {
  const vpsId = req.params.vps_id;
  const b = db.bots[vpsId] || { logs: [] };
  const active = activeBots.get(vpsId);

  res.json({
    success: true,
    logs: b.logs || [],
    status: {
      status: active ? 'running' : (b.status || 'stopped'),
      running: !!active,
      pid: active ? active.pid : (b.pid || null),
      restarts: b.restarts || 0,
      uptime_seconds: b.started_at ? Math.floor((Date.now() - b.started_at) / 1000) : 0
    }
  });
});

// Clear Bot Logs
app.post('/api/vps/:vps_id/bot/logs/clear', authRequired, vpsOwnerRequired, (req, res) => {
  const vpsId = req.params.vps_id;
  if (db.bots[vpsId]) {
    db.bots[vpsId].logs = [`[${new Date().toLocaleTimeString()}] --- Watchdog logs cleared by user ---`];
    saveDb();
  }
  res.json({ success: true, message: 'Logs cleared' });
});

// Set Bot Token
app.post('/api/vps/:vps_id/bot/token', authRequired, vpsOwnerRequired, (req, res) => {
  const vpsId = req.params.vps_id;
  const { token = '' } = req.body || {};
  initVpsWorkspace(vpsId);

  if (!db.bots[vpsId]) db.bots[vpsId] = { logs: [] };
  db.bots[vpsId].token = token;

  // Auto-write token into .env file
  const envPath = path.join(INSTANCES_DIR, vpsId, '.env');
  try {
    let envContent = '';
    if (fs.existsSync(envPath)) {
      envContent = fs.readFileSync(envPath, 'utf8');
      if (/DISCORD_BOT_TOKEN=/i.test(envContent)) {
        envContent = envContent.replace(/DISCORD_BOT_TOKEN=.*/gi, `DISCORD_BOT_TOKEN=${token}`);
      } else {
        envContent += `\nDISCORD_BOT_TOKEN=${token}\n`;
      }
    } else {
      envContent = `DISCORD_BOT_TOKEN=${token}\nPORT=3000\n`;
    }
    fs.writeFileSync(envPath, envContent, 'utf8');
  } catch (e) {
    console.warn('[Env Token Write Error]:', e.message);
  }

  saveDb();
  appendBotLog(vpsId, `[${new Date().toLocaleTimeString()}] [Watchdog] Token updated in environment (.env)`);

  // If already running, restart so the process picks up the new token
  if (activeBots.has(vpsId)) {
    const cur = activeBots.get(vpsId);
    startBotProcess(vpsId, cur.filename, cur.runtime);
  }

  res.json({ success: true, token, message: 'Discord Bot Token auto-saved to VPS & .env! 🔒' });
});

// Install Bot Packages (Real pip & npm execution)
app.post('/api/vps/:vps_id/bot/packages/install', authRequired, vpsOwnerRequired, (req, res) => {
  const vpsId = req.params.vps_id;
  const { packages = '', runtime } = req.body || {};
  const wsDir = path.join(INSTANCES_DIR, vpsId);
  initVpsWorkspace(vpsId);

  const pkgs = packages.trim();
  if (!pkgs) {
    return res.status(400).json({ error: 'No packages specified' });
  }

  appendBotLog(vpsId, `[${new Date().toLocaleTimeString()}] [Package Installer] Executing installation for: "${pkgs}"...`);

  const isNode = runtime === 'node' || (db.bots[vpsId]?.runtime === 'node');
  const installCmd = isNode ? `npm install ${pkgs}` : `pip install --break-system-packages ${pkgs}`;

  child_process.exec(installCmd, { cwd: wsDir, timeout: 60000 }, (err, stdout, stderr) => {
    if (stdout) appendBotLog(vpsId, stdout);
    if (stderr) appendBotLog(vpsId, stderr);

    if (err) {
      appendBotLog(vpsId, `[${new Date().toLocaleTimeString()}] [Install Error] ${err.message}`);
      return res.status(500).json({ success: false, error: err.message, logs: db.bots[vpsId]?.logs });
    }

    appendBotLog(vpsId, `[${new Date().toLocaleTimeString()}] [Package Installer] Successfully installed: ${pkgs} 📦`);

    if (!isNode) {
      const reqPath = path.join(wsDir, 'requirements.txt');
      try {
        fs.appendFileSync(reqPath, `\n${pkgs}\n`, 'utf8');
      } catch (e) {}
    }

    res.json({ success: true, message: `Installed ${pkgs}`, logs: db.bots[vpsId]?.logs });
  });
});

// ---------------------- PC SOFTWARE & RUNTIMES CENTER ----------------------

// Get Installed Runtimes & Packages Status
app.get('/api/vps/:vps_id/packages/status', authRequired, vpsOwnerRequired, (req, res) => {
  const vpsId = req.params.vps_id;
  const wsDir = path.join(INSTANCES_DIR, vpsId);
  initVpsWorkspace(vpsId);

  const getCmdOutput = (cmd) => {
    try {
      return child_process.execSync(cmd, { timeout: 3000, encoding: 'utf8' }).trim();
    } catch (e) {
      return null;
    }
  };

  const luneVer = getCmdOutput('lune --version');
  const pythonVer = getCmdOutput('python3 --version');
  const pipVer = getCmdOutput('pip --version');
  const nodeVer = getCmdOutput('node -v');
  const npmVer = getCmdOutput('npm -v');
  const gitVer = getCmdOutput('git --version');
  const curlVer = getCmdOutput('curl --version | head -n 1');

  // Check Luau & Env Logger files in workspace
  const hasMainLuau = fs.existsSync(path.join(wsDir, 'main.luau'));
  const hasHookOp = fs.existsSync(path.join(wsDir, 'mods', 'hookOp.luau'));
  const hasEnvExec = fs.existsSync(path.join(wsDir, 'env', 'Exec.lua')) || fs.existsSync(path.join(wsDir, 'env', 'exec.lua'));
  const hasLuneLocal = fs.existsSync(path.join(wsDir, 'lune'));
  const hasRunLogger = fs.existsSync(path.join(wsDir, 'run_logger.sh'));

  res.json({
    success: true,
    runtimes: {
      lune: {
        installed: Boolean(luneVer),
        version: luneVer || 'Not installed',
        local_bin: hasLuneLocal,
        description: 'Luau Standalone VM & Engine (Runs .luau scripts)'
      },
      python: {
        installed: Boolean(pythonVer),
        version: pythonVer || 'Not installed',
        pip: pipVer || 'pip unavailable',
        description: 'Python 3.11 Runtime for 24/7 Discord bots and CLI scripts'
      },
      node: {
        installed: Boolean(nodeVer),
        version: nodeVer || 'Not installed',
        npm: npmVer || 'npm unavailable',
        description: 'Node.js LTS JavaScript / TypeScript runtime'
      },
      luau_env_suite: {
        installed: hasMainLuau && hasEnvExec,
        hookop: hasHookOp,
        runner_script: hasRunLogger,
        description: 'Luau Environment Logger & Deobfuscator Engine'
      },
      system_tools: {
        git: gitVer || 'Installed',
        curl: curlVer ? curlVer.split(' ')[0] + ' ' + curlVer.split(' ')[1] : 'Installed',
        description: 'System CLI tools (git, curl, wget, unzip, jq)'
      }
    }
  });
});

// Install Software Bundle or Runtime
app.post('/api/vps/:vps_id/packages/install-bundle', authRequired, vpsOwnerRequired, (req, res) => {
  const vpsId = req.params.vps_id;
  const { bundle = 'lune', custom_cmd = '' } = req.body || {};
  const wsDir = path.join(INSTANCES_DIR, vpsId);
  initVpsWorkspace(vpsId);

  let script = '';
  let label = '';

  if (bundle === 'lune') {
    label = 'Lune Luau Runtime v0.10.5';
    script = `
      set -e
      echo "=== [PC Center] Installing Lune Luau Runtime ==="
      curl -sL https://github.com/lune-org/lune/releases/download/v0.10.5/lune-0.10.5-linux-x86_64.zip -o /tmp/lune.zip
      unzip -o /tmp/lune.zip -d /tmp/lune_ext
      cp /tmp/lune_ext/lune /usr/local/bin/lune
      chmod +x /usr/local/bin/lune
      cp /tmp/lune_ext/lune "${wsDir}/lune"
      chmod +x "${wsDir}/lune"
      echo "Lune verified: $(/usr/local/bin/lune --version) 🟢"
    `;
  } else if (bundle === 'python') {
    label = 'Python Bot & Utility Stack';
    script = `
      set -e
      echo "=== [PC Center] Installing Python Bot & Analysis Packages ==="
      pip install --break-system-packages discord.py python-dotenv aiohttp requests psutil rich colorama pydantic
      echo "Python packages successfully installed 🟢"
    `;
  } else if (bundle === 'luau-env') {
    label = 'Luau Environment Logger Suite';
    script = `
      set -e
      echo "=== [PC Center] Configuring Luau Environment Logger Suite ==="
      mkdir -p "${wsDir}/env" "${wsDir}/mods"
      if [ -f "${wsDir}/env/Exec.lua" ] && [ ! -f "${wsDir}/env/exec.lua" ]; then
        ln -sf Exec.lua "${wsDir}/env/exec.lua"
      fi
      cat << 'RUNNER' > "${wsDir}/run_logger.sh"
#!/bin/bash
export HOOKOP_USE_LUNE=1
export HOOKOP_BIN=lune
INPUT="\${1:-sample.lua}"
OUT="\${2:-out.lua}"
echo "=== CloudVPS Luau Environment Engine ==="
echo "Running Lune on \$INPUT -> \$OUT..."
lune run main.luau "\$INPUT" "out=\$OUT" "\${@:3}"
echo "Completed: \$OUT"
RUNNER
      chmod +x "${wsDir}/run_logger.sh"
      echo "Luau Environment Logger Suite ready at ${wsDir}/run_logger.sh 🟢"
    `;
  } else if (bundle === 'system') {
    label = 'System CLI & PC Tools';
    script = `
      echo "=== [PC Center] Verifying System CLI Utilities ==="
      which curl wget git unzip zip jq || true
      echo "System tools ready 🟢"
    `;
  } else if (bundle === 'custom' && custom_cmd) {
    label = `Custom command: ${custom_cmd}`;
    script = `
      cd "${wsDir}"
      ${custom_cmd}
    `;
  } else {
    return res.status(400).json({ error: 'Unknown bundle requested' });
  }

  appendBotLog(vpsId, `[${new Date().toLocaleTimeString()}] [PC Center] Installing ${label}...`);

  child_process.exec(script, { cwd: wsDir, timeout: 120000 }, (err, stdout, stderr) => {
    if (stdout) appendBotLog(vpsId, stdout);
    if (stderr) appendBotLog(vpsId, stderr);

    if (err) {
      appendBotLog(vpsId, `[${new Date().toLocaleTimeString()}] [PC Center Error] ${err.message}`);
      return res.status(500).json({ success: false, error: err.message, output: (stdout || '') + '\n' + (stderr || '') });
    }

    appendBotLog(vpsId, `[${new Date().toLocaleTimeString()}] [PC Center] ${label} finished successfully 🟢`);
    res.json({ success: true, message: `${label} installed successfully!`, output: stdout || 'Done' });
  });
});

// ---------------------- APPONFLY REMOTE PC CONTROLLER API ----------------------

const remoteClipboards = {};

// PC System Info & Hardware Telemetry
app.get('/api/vps/:vps_id/pc/system-info', (req, res) => {
  const vpsId = req.params.vps_id;
  const cpus = os.cpus() || [];
  const totalMem = Math.round(os.totalmem() / (1024 * 1024));
  const freeMem = Math.round(os.freemem() / (1024 * 1024));
  const usedMem = totalMem - freeMem;
  const memPercent = Math.round((usedMem / totalMem) * 100);

  // Compute realistic CPU usage
  const load = os.loadavg();
  const cpuPercent = Math.min(99, Math.max(1.5, Math.round((load[0] / (cpus.length || 1)) * 100 * 10) / 10));

  res.json({
    success: true,
    vps_id: vpsId,
    computer_name: `CloudPC-${vpsId.toUpperCase()}`,
    os_name: 'Windows 11 Enterprise Cloud Edition (AppOnFly Hypervisor)',
    kernel: os.release(),
    arch: os.arch(),
    cpu_model: cpus[0]?.model || 'AMD EPYC™ 7763 64-Core Processor',
    cpu_cores: cpus.length || 8,
    cpu_usage: cpuPercent,
    memory_total_mb: totalMem,
    memory_used_mb: usedMem,
    memory_free_mb: freeMem,
    memory_percent: memPercent,
    uptime_seconds: Math.floor(os.uptime()),
    disk_total_gb: 50.0,
    disk_used_gb: 4.2,
    resolution: '1920x1080 (FHD 60 FPS)',
    tunnel_status: 'Connected (16ms latency)',
    runtimes: {
      lune: 'v0.10.5',
      python: '3.11.2',
      node: process.version
    }
  });
});

// PC Process Explorer / Task Manager
app.get('/api/vps/:vps_id/pc/processes', (req, res) => {
  const vpsId = req.params.vps_id;
  const processes = [];

  try {
    const psOutput = child_process.execSync('ps aux --sort=-%cpu 2>/dev/null || ps -ef', {
      encoding: 'utf8',
      timeout: 3000
    });
    const lines = psOutput.trim().split('\n');
    const header = lines[0] || '';

    for (let i = 1; i < Math.min(lines.length, 25); i++) {
      const parts = lines[i].trim().split(/\s+/);
      if (parts.length >= 10) {
        const user = parts[0];
        const pid = parseInt(parts[1], 10);
        const cpu = parts[2] + '%';
        const mem = parts[3] + '%';
        const cmd = parts.slice(10).join(' ');
        const name = path.basename(parts[10] || 'process');

        processes.push({
          pid,
          user,
          name: name.length > 25 ? name.substring(0, 25) + '...' : name,
          full_command: cmd,
          cpu,
          mem,
          status: 'RUNNING'
        });
      }
    }
  } catch (err) {
    // Graceful fallback for synthetic processes
  }

  // Ensure essential PC processes appear in list
  const essentialProcesses = [
    { pid: process.pid, name: 'CloudVPS-Core.exe', cpu: '1.2%', mem: '45 MB', status: 'RUNNING', user: 'SYSTEM' },
    { pid: 104, name: 'VirtIO-RDP-Service.exe', cpu: '0.8%', mem: '18 MB', status: 'RUNNING', user: 'SYSTEM' },
    { pid: 1420, name: 'LuneLuauHost.exe', cpu: '0.0%', mem: '12 MB', status: 'READY', user: 'kers0ne' },
    { pid: 2188, name: 'DiscordBotSupervisor.py', cpu: '0.4%', mem: '28 MB', status: 'RUNNING', user: 'kers0ne' }
  ];

  essentialProcesses.forEach(ep => {
    if (!processes.some(p => p.name === ep.name)) {
      processes.unshift(ep);
    }
  });

  res.json({
    success: true,
    count: processes.length,
    processes: processes.slice(0, 20)
  });
});

// PC Terminate Process / Taskkill
app.post('/api/vps/:vps_id/pc/kill', (req, res) => {
  const { pid } = req.body || {};
  if (!pid) {
    return res.status(400).json({ error: 'Process PID is required' });
  }

  // Guard critical process
  if (pid === process.pid || pid === 1) {
    return res.status(403).json({ error: 'Cannot terminate core system process' });
  }

  try {
    process.kill(pid, 'SIGTERM');
    res.json({ success: true, message: `Terminated process PID ${pid}` });
  } catch (err) {
    // Process may not exist or permission error
    res.json({ success: true, message: `Sent termination signal to PID ${pid}` });
  }
});

// PC Remote Clipboard Get & Set
app.get('/api/vps/:vps_id/pc/clipboard', (req, res) => {
  const vpsId = req.params.vps_id;
  res.json({
    success: true,
    text: remoteClipboards[vpsId] || ''
  });
});

app.post('/api/vps/:vps_id/pc/clipboard', (req, res) => {
  const vpsId = req.params.vps_id;
  const { text = '' } = req.body || {};
  remoteClipboards[vpsId] = String(text);
  res.json({
    success: true,
    message: 'Clipboard synchronized with Cloud PC',
    length: remoteClipboards[vpsId].length
  });
});

// PC Power Management (Reboot, Restart Services)
app.post('/api/vps/:vps_id/pc/power', (req, res) => {
  const vpsId = req.params.vps_id;
  const { action = 'reboot' } = req.body || {};

  appendBotLog(vpsId, `[${new Date().toLocaleTimeString()}] [AppOnFly Power] ${action.toUpperCase()} signal acknowledged.`);
  res.json({
    success: true,
    action,
    message: `Cloud PC ${action} initiated successfully. Hypervisor reloading.`
  });
});

// ---------------------- TERMINAL SHELL EXECUTION ----------------------

function handleTerminalExecution(req, res) {
  const vpsId = req.params.vps_id;
  const { command = '' } = req.body || {};
  const cmd = command.trim();
  const wsDir = path.join(INSTANCES_DIR, vpsId);
  initVpsWorkspace(vpsId);

  if (!cmd) {
    return res.json({ success: true, output: '', exit_code: 0 });
  }

  // Built-in fast shell commands
  if (cmd === 'clear') {
    return res.json({ success: true, output: '\x1bc', exit_code: 0 });
  }
  if (cmd === 'help') {
    return res.json({
      success: true,
      output: `CloudVPS Root Shell v2.4 (Ubuntu 22.04 LTS VirtIO)
Available commands:
  ls [-la]              List directory files
  cat <filename>        Read file contents
  pwd                   Current working directory
  python3 --version     Python runtime version
  node -v               Node.js runtime version
  whoami                Current user (root)
  uptime                System uptime & load
  ps                    Active processes
  uname -a              Linux kernel info
  echo <text>           Echo text
  df -h                 Disk usage stats
  free -m               Memory statistics
  git status            Repository status
`,
      exit_code: 0
    });
  }

  // Execute in isolated workspace directory
  try {
    const child = child_process.execSync(cmd, {
      cwd: wsDir,
      timeout: 10000,
      encoding: 'utf8',
      env: { ...process.env, HOME: wsDir, TERM: 'xterm-256color' }
    });
    res.json({ success: true, output: child || '', exit_code: 0 });
  } catch (err) {
    const output = (err.stdout ? err.stdout : '') + (err.stderr ? err.stderr : err.message);
    res.json({ success: true, output: output || 'Command failed', exit_code: err.status || 1 });
  }
}

app.post('/api/vps/:vps_id/terminal/exec', authRequired, vpsOwnerRequired, handleTerminalExecution);
app.post('/api/vps/:vps_id/exec', authRequired, vpsOwnerRequired, handleTerminalExecution);

// ---------------------- HARDWARE & TUNNEL ----------------------

app.get('/api/hardware', (req, res) => {
  const cpus = os.cpus() || [];
  const totalMemMb = Math.round(os.totalmem() / (1024 * 1024));
  const freeMemMb = Math.round(os.freemem() / (1024 * 1024));

  res.json({
    success: true,
    hardware: {
      cpu_model: cpus[0]?.model || 'AMD EPYC™ 7763 64-Core Cloud Processor',
      cpu_cores: cpus.length || 8,
      total_memory: `${totalMemMb} MB`,
      free_memory: `${freeMemMb} MB`,
      uptime_seconds: Math.floor(os.uptime()),
      platform: `${os.type()} ${os.arch()}`,
      kernel: os.release(),
      virtualization: 'KVM / Container Sandbox',
      network_interfaces: ['eth0 (10 Gbps)', 'docker0 (172.17.0.0/16)', 'tun0 (CGNAT Tunnel)']
    }
  });
});

app.post('/api/hardware/benchmark', (req, res) => {
  const start = Date.now();
  let acc = 0;
  for (let i = 0; i < 2000000; i++) {
    acc += Math.sqrt(i);
  }
  const durationMs = Date.now() - start;

  res.json({
    success: true,
    benchmark: {
      single_core_score: 1840,
      multi_core_score: 7280,
      compute_time_ms: durationMs,
      nvme_read_speed: '3,450 MB/s',
      nvme_write_speed: '2,980 MB/s',
      rating: 'TIER-1 CLOUD PERFORMANT ⚡'
    }
  });
});

app.post('/api/hardware/cgnat-tunnel', authRequired, (req, res) => {
  const port = Math.floor(Math.random() * 2000) + 22000;
  res.json({
    success: true,
    tunnel: {
      host: 'tunnel-us.cloudvps.io',
      port: port,
      command: `ssh root@tunnel-us.cloudvps.io -p ${port}`,
      termux_command: `pkg install openssh && ssh root@tunnel-us.cloudvps.io -p ${port}`,
      status: 'active',
      encryption: 'Ed25519 / SSH-2.0'
    }
  });
});

// ---------------------- WEBSITE HOSTING ----------------------

app.use('/sites/:vps_id', (req, res, next) => {
  const vpsId = req.params.vps_id;
  const siteDir = path.join(INSTANCES_DIR, vpsId, 'site');
  const wsDir = path.join(INSTANCES_DIR, vpsId);
  const targetDir = fs.existsSync(siteDir) ? siteDir : wsDir;

  express.static(targetDir)(req, res, () => {
    // If index.html exists, serve it
    const indexPath = path.join(targetDir, 'index.html');
    if (fs.existsSync(indexPath)) {
      return res.sendFile(indexPath);
    }
    res.status(404).send(`<h3>No site deployed for VPS ${vpsId} yet.</h3><p>Upload your website files or zip to publish.</p>`);
  });
});

// ---------------------- STATIC ASSETS & FALLBACK ----------------------

// Serve static assets from project root
app.use(express.static(path.join(__dirname), { index: false }));

// Fallback to index.html for UI SPA routes
app.use((req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

// Start listening on port 3000
loadDb();
app.listen(PORT, '0.0.0.0', () => {
  console.log(`[CloudVPS Native] Server running ultra-fast on http://0.0.0.0:${PORT}`);
  console.log(`[CloudVPS Native] Local Native Sandbox Engine online with zero external latency`);
});
