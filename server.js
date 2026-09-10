const { spawn } = require('child_process');
const path = require('path');

// Determine port: in AI Studio the app must listen on 3000.
// If run on Render or elsewhere, PORT may be provided by environment.
const targetPort = process.env.AI_STUDIO_PORT || process.env.PORT || '3000';
// If PORT is 8080 (which nginx uses in this container), we force 3000.
const appPort = targetPort === '8080' ? '3000' : targetPort;

console.log(`[CloudVPS Launcher] Starting CloudVPS backend on port ${appPort}...`);

const env = {
  ...process.env,
  PORT: appPort,
  PYTHONUNBUFFERED: '1',
};

const pythonProcess = spawn('python3', [path.join(__dirname, 'app.py')], {
  env,
  stdio: 'inherit',
  cwd: __dirname,
});

pythonProcess.on('error', (err) => {
  console.error('[CloudVPS Launcher] Failed to start python backend:', err);
  process.exit(1);
});

pythonProcess.on('exit', (code, signal) => {
  console.log(`[CloudVPS Launcher] Backend exited with code ${code} signal ${signal}`);
  process.exit(code || 0);
});

const cleanup = () => {
  if (pythonProcess && !pythonProcess.killed) {
    pythonProcess.kill('SIGTERM');
  }
};

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
