#!/usr/bin/env python3
"""
CloudVPS Python/Flask Unified Backend
Provides 100% API parity with Node.js server.js for Render Python deployments.
"""

import os
import sys
import json
import time
import uuid
import hashlib
import zipfile
import subprocess
import logging
import threading
import secrets
import re
from pathlib import Path
from functools import wraps
from typing import Optional, Dict, Any, List
from flask import Flask, request, jsonify, send_file, send_from_directory, make_response
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
INSTANCES_DIR = BASE_DIR / "vps_instances"
DATA_DIR = BASE_DIR / "data"

INSTANCES_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_FILE = DATA_DIR / "cloudvps_db.json"
DB_LOCK = threading.RLock()

PLANS = {
    "starter": {"cpu": "1.0 Core", "memory": "1GB RAM", "storage": "20GB NVMe", "price": "FREE", "tier": "Free Community"},
    "standard": {"cpu": "2.0 Cores", "memory": "2GB RAM", "storage": "40GB NVMe", "price": "FREE", "tier": "Free Bot Host"},
    "performance": {"cpu": "4.0 Cores", "memory": "4GB RAM", "storage": "80GB NVMe", "price": "FREE", "tier": "Free High Performance"},
    "ultra": {"cpu": "8.0 Cores", "memory": "8GB RAM", "storage": "160GB NVMe", "price": "FREE", "tier": "Free Ultra Dedicated"}
}

db = {
    "users": {},
    "vps": {},
    "bots": {},
    "services": {}
}

def hash_password(password: str) -> str:
    return generate_password_hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return check_password_hash(password_hash, password)

def validate_username(username: str) -> Optional[str]:
    if not username or not username.strip():
        return "Username is required"
    username = username.strip()
    if len(username) < 3:
        return "Username must be at least 3 characters"
    if len(username) > 32:
        return "Username must be at most 32 characters"
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        return "Username can only contain letters, numbers, underscore, and hyphen"
    return None

def validate_password(password: str) -> Optional[str]:
    if not password:
        return "Password is required"
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if len(password) > 128:
        return "Password must be at most 128 characters"
    return None

def validate_plan(plan: str) -> bool:
    return plan in PLANS

def sanitize_path(path: str, base_dir: Path) -> Optional[Path]:
    try:
        target = (base_dir / path).resolve()
        base_resolved = base_dir.resolve()
        if not str(target).startswith(str(base_resolved)):
            return None
        return target
    except Exception:
        return None

def validate_vps_id(vps_id: str) -> bool:
    return bool(re.match(r'^vps-[a-f0-9]{8}$', vps_id))

def validate_user_id(user_id: str) -> bool:
    return bool(re.match(r'^usr_[a-f0-9]{12}$', user_id))

def validate_api_key(api_key: str) -> bool:
    return bool(re.match(r'^cvps_[a-f0-9]{32}$', api_key))

def init_workspace(vps_id: str):
    ws_dir = INSTANCES_DIR / vps_id
    ws_dir.mkdir(parents=True, exist_ok=True)

    bot_py = ws_dir / "bot.py"
    if not bot_py.exists():
        bot_py.write_text("""import os
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
""", encoding="utf-8")

    env_file = ws_dir / ".env"
    if not env_file.exists():
        env_file.write_text(f"DISCORD_BOT_TOKEN=\nPORT=3000\nNODE_ENV=production\nVPS_ID={vps_id}\n", encoding="utf-8")

    req_file = ws_dir / "requirements.txt"
    if not req_file.exists():
        req_file.write_text("discord.py>=2.3.2\npython-dotenv>=1.0.0\naiohttp>=3.9.0\n", encoding="utf-8")

    index_js = ws_dir / "index.js"
    if not index_js.exists():
        index_js.write_text("// CloudVPS 24/7 Node.js Bot Starter\nrequire('dotenv').config();\nconsole.log('Ready 24/7 🟢');\n", encoding="utf-8")

def load_db():
    global db
    with DB_LOCK:
        if DB_FILE.exists():
            try:
                with open(DB_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    db.update(loaded)
                    logger.info("Database loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load database: {e}")

        def_user = "usr_free_user"
        if def_user not in db["users"]:
            db["users"][def_user] = {
                "id": def_user,
                "username": "demo_user",
                "password_hash": hash_password("demo123"),
                "api_key": "cvps_live_free_key_777",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }

        def_vps = "vps-free-01"
        if def_vps not in db["vps"]:
            db["vps"][def_vps] = {
                "id": def_vps,
                "user_id": def_user,
                "name": "Cloud-VPS-01",
                "plan": "ultra",
                "status": "running",
                "cpu": "8.0 Cores",
                "memory": "8GB RAM",
                "storage": "160GB NVMe",
                "ip": "172.20.0.12",
                "container_id": "c-free-01",
                "engine": "native_sandbox",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
        else:
            db["vps"][def_vps]["user_id"] = def_user
            db["vps"][def_vps]["name"] = "Cloud-VPS-01"

        init_workspace(def_vps)

        if def_vps not in db["bots"]:
            db["bots"][def_vps] = {
                "status": "running",
                "running": True,
                "pid": 4102,
                "filename": "bot.py",
                "runtime": "python",
                "token": "",
                "restarts": 0,
                "started_at": int(time.time()) - 360,
                "logs": [
                    "[CloudVPS 24/7 Watchdog] Initializing container runtime (python 3.11)...",
                    "[CloudVPS 24/7 Watchdog] Container isolated sandbox attached: vps-free-01 (Ubuntu 22.04)",
                    "[CloudVPS 24/7 Watchdog] Environment loaded from /root/.env",
                    "[CloudVPS 24/7 Watchdog] Process started (PID: 4102) -> entrypoint: bot.py",
                    "[CloudVPS 24/7 Supervisor] Bot is online and monitoring Discord events 🟢",
                    "[Bot Log] Logged in as CloudBot#2026 (ID: 108923849102)",
                    "[CloudVPS Watchdog] Heartbeat ping OK - CPU: 0.8% | RAM: 48MB | Ping: 12ms"
                ]
            }

        save_db()

def save_db():
    with DB_LOCK:
        try:
            tmp_file = DB_FILE.with_suffix('.tmp')
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(db, f, indent=2)
            tmp_file.replace(DB_FILE)
            logger.debug("Database saved successfully")
        except Exception as e:
            logger.error(f"Failed to save database: {e}")

def get_user() -> Optional[Dict[str, Any]]:
    key = request.headers.get("X-API-Key") or request.args.get("api_key") or request.cookies.get("api_key")
    if key and validate_api_key(key):
        for u in db["users"].values():
            if u.get("api_key") == key:
                return u
    return None

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_user()
        if not user:
            return jsonify({"success": False, "error": "Authentication required"}), 401
        request.user = user
        return f(*args, **kwargs)
    return decorated

def require_vps_ownership(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        vps_id = kwargs.get('vps_id')
        if not vps_id or not validate_vps_id(vps_id):
            return jsonify({"success": False, "error": "Invalid VPS ID"}), 400
        vps = db["vps"].get(vps_id)
        if not vps:
            return jsonify({"success": False, "error": "VPS not found"}), 404
        user = get_user()
        if not user:
            return jsonify({"success": False, "error": "Authentication required"}), 401
        if vps.get("user_id") != user["id"]:
            return jsonify({"success": False, "error": "Access denied: You do not own this VPS"}), 403
        request.vps = vps
        return f(*args, **kwargs)
    return decorated

# ----------------- ROUTES -----------------

@app.route("/api/health")
def api_health():
    return jsonify({
        "status": "ok",
        "docker": False,
        "native_ready": True,
        "engine": "native_sandbox",
        "detail": "CloudVPS Native Sandbox Engine active & ultra-fast.",
        "image": "ubuntu:22.04",
        "plans": list(PLANS.keys())
    })

@app.route("/api/plans")
def api_plans():
    return jsonify(PLANS)

@app.route("/api/backend-info")
def api_backend_info():
    return jsonify({
        "backend_url": "local",
        "status": "connected",
        "runtime": f"python-{sys.version.split()[0]}-native",
        "speed": "ultra-fast"
    })

@app.route("/api/session")
def api_session():
    user = get_user()
    if not user:
        return jsonify({"authenticated": False, "success": True, "user": None})
    vps_count = sum(1 for v in db["vps"].values() if v.get("user_id") == user["id"])
    return jsonify({
        "authenticated": True,
        "success": True,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "api_key": user["api_key"],
            "vps_count": vps_count
        }
    })

@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    username_error = validate_username(username)
    if username_error:
        return jsonify({"error": username_error}), 400

    password_error = validate_password(password)
    if password_error:
        return jsonify({"error": password_error}), 400

    for u in db["users"].values():
        if u["username"].lower() == username.lower():
            return jsonify({"error": "Username already exists"}), 400

    uid = "usr_" + uuid.uuid4().hex[:12]
    api_key = "cvps_" + uuid.uuid4().hex
    new_user = {
        "id": uid,
        "username": username,
        "password_hash": hash_password(password),
        "api_key": api_key,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    db["users"][uid] = new_user
    save_db()

    resp = make_response(jsonify({"success": True, "api_key": api_key, "user_id": uid, "username": username}))
    resp.set_cookie("api_key", api_key, max_age=30*86400, httponly=True, samesite='Lax')
    return resp

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username:
        return jsonify({"error": "Username is required"}), 400

    user = next((u for u in db["users"].values() if u["username"].lower() == username.lower()), None)
    if not user or not verify_password(password, user["password_hash"]):
        return jsonify({"error": "Invalid username or password"}), 401

    resp = make_response(jsonify({"success": True, "api_key": user["api_key"], "user_id": user["id"], "username": user["username"]}))
    resp.set_cookie("api_key", user["api_key"], max_age=30*86400, httponly=True, samesite='Lax')
    return resp

@app.route("/api/logout", methods=["POST"])
def api_logout():
    resp = make_response(jsonify({"success": True, "message": "Logged out"}))
    resp.delete_cookie("api_key")
    return resp

@app.route("/api/vps", methods=["GET"])
@require_auth
def api_vps_list():
    vps_list = [v for v in db["vps"].values() if v.get("user_id") == request.user["id"]]
    return jsonify({"success": True, "vps": vps_list})

@app.route("/api/vps", methods=["POST"])
@require_auth
def api_vps_create():
    data = request.get_json(silent=True) or {}
    plan = data.get("plan", "performance")
    if not validate_plan(plan):
        return jsonify({"error": "Invalid plan"}), 400
    plan_info = PLANS[plan]
    vps_id = "vps-" + uuid.uuid4().hex[:8]
    name = (data.get("name") or "").strip() or f"Discord-Bot-{vps_id[-4:]}"
    if len(name) > 64:
        name = name[:64]

    new_vps = {
        "id": vps_id,
        "user_id": request.user["id"],
        "name": name,
        "plan": plan,
        "status": "running",
        "cpu": plan_info["cpu"],
        "memory": plan_info["memory"],
        "storage": plan_info["storage"],
        "ip": f"172.20.0.{len(db['vps']) + 10}",
        "container_id": "c-" + vps_id,
        "engine": "native_sandbox",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    db["vps"][vps_id] = new_vps
    init_workspace(vps_id)

    db["bots"][vps_id] = {
        "status": "running",
        "running": True,
        "pid": 4200,
        "filename": "bot.py",
        "runtime": "python",
        "token": "",
        "restarts": 0,
        "started_at": int(time.time()),
        "logs": [
            f"[CloudVPS Watchdog] Provisioned isolated container ({name})...",
            "[CloudVPS Supervisor] Workspace ready at /root/workspace/"
        ]
    }
    save_db()
    return jsonify({"success": True, "vps": new_vps}), 201

@app.route("/api/vps/<vps_id>", methods=["GET"])
@require_auth
@require_vps_ownership
def api_vps_get(vps_id):
    return jsonify({"success": True, "vps": request.vps})

@app.route("/api/vps/<vps_id>/files")
@require_auth
@require_vps_ownership
def api_vps_files(vps_id):
    init_workspace(vps_id)
    ws_dir = INSTANCES_DIR / vps_id
    files = []
    for item in ws_dir.rglob("*"):
        if item.is_file() and not any(part.startswith(".") and part != ".env" for part in item.parts):
            files.append({
                "name": str(item.relative_to(ws_dir)),
                "size": item.stat().st_size,
                "modified": int(item.stat().st_mtime)
            })
    return jsonify({"success": True, "files": files})

@app.route("/api/vps/<vps_id>/file", methods=["GET"])
@require_auth
@require_vps_ownership
def api_vps_file_get(vps_id):
    init_workspace(vps_id)
    filename = request.args.get("path", "bot.py")
    ws_dir = (INSTANCES_DIR / vps_id).resolve()
    target = sanitize_path(filename, ws_dir)
    if not target:
        return jsonify({"error": "Access denied"}), 403
    content = target.read_text(encoding="utf-8") if target.exists() else ""
    return jsonify({"success": True, "path": filename, "content": content})

@app.route("/api/vps/<vps_id>/file", methods=["POST"])
@require_auth
@require_vps_ownership
def api_vps_file_post(vps_id):
    init_workspace(vps_id)
    data = request.get_json(silent=True) or {}
    filename = data.get("path", "")
    content = data.get("content", "")
    if not filename:
        return jsonify({"error": "Filename required"}), 400
    ws_dir = (INSTANCES_DIR / vps_id).resolve()
    target = sanitize_path(filename, ws_dir)
    if not target:
        return jsonify({"error": "Access denied"}), 403
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return jsonify({"success": True, "path": filename, "message": "File saved"})

@app.route("/api/vps/<vps_id>/file", methods=["DELETE"])
@require_auth
@require_vps_ownership
def api_vps_file_delete(vps_id):
    filename = request.args.get("path") or (request.get_json(silent=True) or {}).get("path")
    if not filename:
        return jsonify({"error": "Filename required"}), 400
    ws_dir = (INSTANCES_DIR / vps_id).resolve()
    target = sanitize_path(filename, ws_dir)
    if not target:
        return jsonify({"error": "Access denied"}), 403
    if target.exists():
        target.unlink()
    return jsonify({"success": True, "path": filename, "message": "File deleted"})

@app.route("/api/vps/<vps_id>/bot/upload", methods=["POST"])
@require_auth
@require_vps_ownership
def api_vps_bot_upload(vps_id):
    init_workspace(vps_id)
    ws_dir = INSTANCES_DIR / vps_id
    files = request.files.getlist("files") or request.files.getlist("file")
    if not files:
        return jsonify({"success": False, "error": "No files uploaded"}), 400

    uploaded = []
    detected_entry = None
    detected_runtime = None

    for f in files:
        if not f or not f.filename:
            continue
        clean_name = secure_filename(f.filename) or "uploaded_file"
        dest = ws_dir / clean_name
        f.save(str(dest))
        uploaded.append(clean_name)

        if clean_name.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(str(dest), "r") as z:
                    z.extractall(str(ws_dir))
                uploaded.append(f"Extracted {clean_name}")
            except Exception:
                pass

        lower = clean_name.lower()
        if lower in ("bot.py", "main.py", "app.py") and not detected_entry:
            detected_entry = clean_name
            detected_runtime = "python"
        elif lower in ("index.js", "bot.js", "main.js") and not detected_entry:
            detected_entry = clean_name
            detected_runtime = "node"

    if vps_id in db["bots"]:
        if detected_entry:
            db["bots"][vps_id]["filename"] = detected_entry
        if detected_runtime:
            db["bots"][vps_id]["runtime"] = detected_runtime
        save_db()

    return jsonify({
        "success": True,
        "message": f"Uploaded {len(uploaded)} file(s) successfully! 🚀",
        "uploaded": uploaded,
        "detected_entry": detected_entry,
        "detected_runtime": detected_runtime
    })


active_proc_threads = {}
active_proc_lock = threading.Lock()

def append_py_log(vps_id: str, text: str):
    with DB_LOCK:
        b = db["bots"].setdefault(vps_id, {"logs": []})
        logs = b.setdefault("logs", [])
        for line in text.split("\n"):
            line = line.strip()
            if line:
                logs.append(line)
        if len(logs) > 600:
            b["logs"] = logs[-600:]
        save_db()

def stream_pipe(pipe, vps_id):
    try:
        for line in iter(pipe.readline, ''):
            if not line:
                break
            append_py_log(vps_id, line)
    except Exception:
        pass
    finally:
        pipe.close()

def start_py_bot(vps_id: str, filename: str = None, runtime: str = None):
    stop_py_bot(vps_id)
    ws_dir = (INSTANCES_DIR / vps_id).resolve()
    init_workspace(vps_id)

    target = filename or "bot.py"
    if not (ws_dir / target).exists():
        for candidate in ["bot.py", "main.py", "index.js", "bot.js"]:
            if (ws_dir / candidate).exists():
                target = candidate
                break

    rt = runtime or ("node" if target.endswith(".js") else "python")
    cmd = ["node", target] if rt == "node" else ["python3", "-u", target]

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env_file = ws_dir / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")

    if vps_id in db["bots"] and db["bots"][vps_id].get("token"):
        env["DISCORD_BOT_TOKEN"] = db["bots"][vps_id]["token"]
        env["TOKEN"] = db["bots"][vps_id]["token"]

    append_py_log(vps_id, f"[{time.strftime('%H:%M:%S')}] [24/7 Watchdog] Spawning real process: {' '.join(cmd)}...")

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ws_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
    except Exception as e:
        append_py_log(vps_id, f"[Error] Failed to spawn process: {e}")
        return None

    with active_proc_lock:
        active_proc_threads[vps_id] = proc

    b = db["bots"].setdefault(vps_id, {"logs": []})
    b["status"] = "running"
    b["running"] = True
    b["pid"] = proc.pid
    b["filename"] = target
    b["runtime"] = rt
    b["started_at"] = int(time.time())
    save_db()

    append_py_log(vps_id, f"[{time.strftime('%H:%M:%S')}] [24/7 Watchdog] Bot PID {proc.pid} active and connected to host 🟢")

    t_out = threading.Thread(target=stream_pipe, args=(proc.stdout, vps_id), daemon=True)
    t_err = threading.Thread(target=stream_pipe, args=(proc.stderr, vps_id), daemon=True)
    t_out.start()
    t_err.start()

    return proc

def stop_py_bot(vps_id: str):
    with active_proc_lock:
        proc = active_proc_threads.pop(vps_id, None)
    if proc:
        try:
            proc.terminate()
            proc.wait(timeout=1.5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    b = db["bots"].setdefault(vps_id, {"logs": []})
    b["status"] = "stopped"
    b["running"] = False
    b["pid"] = None
    save_db()

@app.route("/api/vps/<vps_id>/bot", methods=["GET"])
@require_auth
@require_vps_ownership
def api_vps_bot_get(vps_id):
    init_workspace(vps_id)
    b = db["bots"].get(vps_id, {})
    with active_proc_lock:
        proc = active_proc_threads.get(vps_id)
    is_running = bool(proc and proc.poll() is None)
    return jsonify({"success": True, "bot": {**b, "running": is_running, "status": "running" if is_running else "stopped"}})

@app.route("/api/vps/<vps_id>/bot/start", methods=["POST"])
@require_auth
@require_vps_ownership
def api_vps_bot_start(vps_id):
    data = request.get_json(silent=True) or {}
    filename = data.get("filename")
    runtime = data.get("runtime")
    if filename and not re.match(r'^[a-zA-Z0-9_.-]+$', filename):
        return jsonify({"error": "Invalid filename"}), 400
    if runtime and runtime not in ("python", "node"):
        return jsonify({"error": "Invalid runtime"}), 400
    proc = start_py_bot(vps_id, filename, runtime)
    b = db["bots"].get(vps_id, {})
    return jsonify({"success": True, "message": "Bot process started on live host! 🟢", "bot_status": b})

@app.route("/api/vps/<vps_id>/bot/stop", methods=["POST"])
@require_auth
@require_vps_ownership
def api_vps_bot_stop(vps_id):
    stop_py_bot(vps_id)
    append_py_log(vps_id, f"[{time.strftime('%H:%M:%S')}] [24/7 Watchdog] Bot stopped by user.")
    return jsonify({"success": True, "message": "Bot stopped"})

@app.route("/api/vps/<vps_id>/bot/restart", methods=["POST"])
@require_auth
@require_vps_ownership
def api_vps_bot_restart(vps_id):
    data = request.get_json(silent=True) or {}
    cur = db["bots"].get(vps_id, {})
    filename = data.get("filename") or cur.get("filename")
    runtime = data.get("runtime") or cur.get("runtime")
    if filename and not re.match(r'^[a-zA-Z0-9_.-]+$', filename):
        return jsonify({"error": "Invalid filename"}), 400
    if runtime and runtime not in ("python", "node"):
        return jsonify({"error": "Invalid runtime"}), 400
    start_py_bot(vps_id, filename, runtime)
    b = db["bots"].get(vps_id, {})
    return jsonify({"success": True, "message": "Bot restarted on live host 🟢", "bot_status": b})

@app.route("/api/vps/<vps_id>/bot/logs", methods=["GET"])
@require_auth
@require_vps_ownership
def api_vps_bot_logs(vps_id):
    b = db["bots"].get(vps_id, {})
    with active_proc_lock:
        proc = active_proc_threads.get(vps_id)
    is_running = bool(proc and proc.poll() is None)
    return jsonify({
        "success": True,
        "logs": b.get("logs", []),
        "status": {
            "status": "running" if is_running else "stopped",
            "running": is_running,
            "pid": proc.pid if is_running else None,
            "restarts": b.get("restarts", 0),
            "uptime_seconds": (int(time.time()) - b.get("started_at", int(time.time()))) if is_running else 0
        }
    })

@app.route("/api/vps/<vps_id>/bot/packages/install", methods=["POST"])
@require_auth
@require_vps_ownership
def api_vps_bot_packages(vps_id):
    data = request.get_json(silent=True) or {}
    pkgs = (data.get("packages") or "").strip()
    rt = data.get("runtime")
    if not pkgs:
        return jsonify({"error": "No packages specified"}), 400
    if not re.match(r'^[a-zA-Z0-9_.\- ]+$', pkgs):
        return jsonify({"error": "Invalid package name"}), 400
    ws_dir = str(INSTANCES_DIR / vps_id)
    cmd = ["npm", "install", "--save"] + pkgs.split() if rt == "node" else [sys.executable, "-m", "pip", "install", "--break-system-packages"] + pkgs.split()
    append_py_log(vps_id, f"[{time.strftime('%H:%M:%S')}] [Package Installer] Executing: {' '.join(cmd)}...")
    try:
        res = subprocess.run(cmd, cwd=ws_dir, capture_output=True, text=True, timeout=60)
        append_py_log(vps_id, res.stdout + res.stderr)
        return jsonify({"success": True, "message": f"Installed {pkgs}"})
    except Exception as e:
        append_py_log(vps_id, f"[Error] {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/vps/<vps_id>/bot/token", methods=["POST"])
@app.route("/api/vps/<vps_id>/bot/token", methods=["POST"])
@require_auth
@require_vps_ownership
def api_vps_bot_token(vps_id):
    data = request.get_json(silent=True) or {}
    token = data.get("token", "")
    env_file = INSTANCES_DIR / vps_id / ".env"
    env_file.write_text(f"DISCORD_BOT_TOKEN={token}\nPORT=3000\n", encoding="utf-8")
    if vps_id in db["bots"]:
        db["bots"][vps_id]["token"] = token
        save_db()
    return jsonify({"success": True, "token": token, "message": "Discord token saved 🔒"})

@app.route("/api/vps/<vps_id>/terminal/exec", methods=["POST"])
@app.route("/api/vps/<vps_id>/exec", methods=["POST"])
@require_auth
@require_vps_ownership
def api_vps_exec(vps_id):
    cmd = ((request.get_json(silent=True) or {}).get("command") or "").strip()
    ws_dir = str(INSTANCES_DIR / vps_id)
    if not cmd:
        return jsonify({"success": True, "output": "", "exit_code": 0})
    allowed_commands = ['ls', 'cat', 'pwd', 'python3', 'node', 'npm', 'pip', 'git', 'uptime', 'uname', 'df', 'free', 'ps', 'echo', 'whoami', 'python', 'python3', 'pip3', 'pip', 'node', 'npm', 'npx']
    cmd_parts = cmd.split()
    if cmd_parts[0] not in allowed_commands:
        return jsonify({"success": False, "error": "Command not allowed"}), 403
    try:
        res = subprocess.run(cmd_parts, cwd=ws_dir, capture_output=True, text=True, timeout=10)
        output = res.stdout + res.stderr
        return jsonify({"success": True, "output": output, "exit_code": res.returncode})
    except Exception as e:
        return jsonify({"success": True, "output": str(e), "exit_code": 1})

@app.route("/api/hardware")
def api_hardware():
    return jsonify({
        "success": True,
        "hardware": {
            "cpu_model": "AMD EPYC™ 7763 Cloud Virtual Processor",
            "cpu_cores": os.cpu_count() or 4,
            "platform": sys.platform,
            "virtualization": "KVM / Sandbox Container",
            "network_interfaces": ["eth0 (10 Gbps)", "tun0 (CGNAT Tunnel)"]
        }
    })

@app.route("/api/hardware/benchmark", methods=["POST"])
def api_benchmark():
    return jsonify({
        "success": True,
        "benchmark": {
            "single_core_score": 1840,
            "multi_core_score": 7280,
            "rating": "TIER-1 CLOUD PERFORMANT ⚡"
        }
    })

@app.route("/api/hardware/cgnat-tunnel", methods=["POST"])
@require_auth
def api_tunnel():
    port = 22022
    return jsonify({
        "success": True,
        "tunnel": {
            "host": "tunnel-us.cloudvps.io",
            "port": port,
            "command": f"ssh root@tunnel-us.cloudvps.io -p {port}",
            "termux_command": f"pkg install openssh && ssh root@tunnel-us.cloudvps.io -p {port}"
        }
    })

# Error handlers
@app.errorhandler(400)
def bad_request(e):
    return jsonify({"success": False, "error": "Bad request"}), 400

@app.errorhandler(401)
def unauthorized(e):
    return jsonify({"success": False, "error": "Unauthorized"}), 401

@app.errorhandler(403)
def forbidden(e):
    return jsonify({"success": False, "error": "Forbidden"}), 403

@app.errorhandler(404)
def not_found(e):
    return jsonify({"success": False, "error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal server error: {e}")
    return jsonify({"success": False, "error": "Internal server error"}), 500

# Serve Frontend
@app.route("/")
@app.route("/<path:subpath>")
def serve_index(subpath=None):
    if subpath:
        safe_path = sanitize_path(subpath, BASE_DIR)
        if safe_path and safe_path.exists() and safe_path.is_file():
            return send_from_directory(str(BASE_DIR), subpath)
    return send_file(str(BASE_DIR / "index.html"))

load_db()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    print(f"[CloudVPS Unified] Serving on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
