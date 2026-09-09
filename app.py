from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import docker_utils
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Fake user system (no database needed for demo)
users = {}
sessions = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username')
    password = request.form.get('password')
    if username in users:
        return jsonify({'error': 'Username already exists'}), 400
    users[username] = {'password': password}
    return jsonify({'success': True, 'message': 'Account created!'})

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    if username not in users or users[username]['password'] != password:
        return jsonify({'error': 'Invalid credentials'}), 401
    session['user'] = username
    return jsonify({'success': True, 'redirect': '/dashboard'})

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/')
    containers = docker_utils.get_user_containers(session['user'])
    return render_template('dashboard.html', user=session['user'], containers=containers)

@app.route('/api/create', methods=['POST'])
def create_vps():
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    plan = request.json.get('plan', 'starter')
    result = docker_utils.create_vps_container(session['user'], plan)
    return jsonify(result)

@app.route('/api/stop/<container_id>', methods=['POST'])
def stop_vps(container_id):
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    return jsonify(docker_utils.stop_container(container_id))

@app.route('/api/start/<container_id>', methods=['POST'])
def start_vps(container_id):
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    return jsonify(docker_utils.start_container(container_id))

@app.route('/api/delete/<container_id>', methods=['POST'])
def delete_vps(container_id):
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    return jsonify(docker_utils.delete_container(container_id))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
