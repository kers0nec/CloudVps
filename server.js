const express = require('express');
const axios = require('axios');
const path = require('path');
const dotenv = require('dotenv');

dotenv.config();

const app = express();
const PORT = 3000;
const BACKEND_URL = (process.env.BACKEND_URL || 'https://cloudvps-7df8.onrender.com').replace(/\/+$/, '');

console.log(`[CloudVPS Proxy] Booting Node.js web server with Render backend: ${BACKEND_URL}`);

// Fallback plans if remote is waking up
const FALLBACK_PLANS = {
  starter: { cpu: '1.0 Core', memory: '1GB RAM', storage: '20GB NVMe', price: 'FREE', tier: 'Free Community' },
  standard: { cpu: '2.0 Cores', memory: '2GB RAM', storage: '40GB NVMe', price: 'FREE', tier: 'Free Bot Host' },
  performance: { cpu: '4.0 Cores', memory: '4GB RAM', storage: '80GB NVMe', price: 'FREE', tier: 'Free High Performance' },
  ultra: { cpu: '8.0 Cores', memory: '8GB RAM', storage: '160GB NVMe', price: 'FREE', tier: 'Free Ultra Dedicated' },
};

// Raw body parser for /api routes to preserve binary/form-data/JSON payloads
app.use('/api', express.raw({ type: '*/*', limit: '50mb' }));

// Dedicated backend info route
app.get('/api/backend-info', (req, res) => {
  res.json({
    backend_url: BACKEND_URL,
    status: 'connected',
    runtime: 'node-22-proxy',
  });
});

// Proxy all /api requests to Render backend
app.use('/api', async (req, res) => {
  const targetPath = req.originalUrl;
  const targetUrl = `${BACKEND_URL}${targetPath}`;

  const forwardHeaders = { ...req.headers };
  delete forwardHeaders['host'];
  delete forwardHeaders['connection'];
  delete forwardHeaders['content-length'];

  try {
    const hasBody = req.method !== 'GET' && req.method !== 'HEAD' && req.body && req.body.length > 0;

    const response = await axios({
      method: req.method,
      url: targetUrl,
      headers: forwardHeaders,
      data: hasBody ? req.body : undefined,
      validateStatus: () => true, // Forward all status codes directly
      responseType: 'stream',
      timeout: 45000,
    });

    res.status(response.status);

    for (const [key, value] of Object.entries(response.headers)) {
      const lower = key.toLowerCase();
      // Skip chunked/compression headers that might conflict with streaming
      if (lower !== 'transfer-encoding' && lower !== 'content-encoding') {
        res.setHeader(key, value);
      }
    }

    response.data.pipe(res);
  } catch (err) {
    console.error(`[CloudVPS Proxy Error] ${req.method} ${targetPath} ->`, err.message);

    // Fallbacks for critical landing endpoints if backend is cold-booting
    if (req.path === '/health' || req.originalUrl === '/api/health') {
      return res.status(200).json({
        status: 'connecting',
        detail: `CloudVPS backend on Render (${BACKEND_URL}) is waking up. Retry in a few seconds.`,
        docker: false,
        engine: 'native_sandbox',
        plans: Object.keys(FALLBACK_PLANS),
        native_ready: true,
      });
    }

    if (req.path === '/plans' || req.originalUrl === '/api/plans') {
      return res.status(200).json(FALLBACK_PLANS);
    }

    res.status(502).json({
      error: 'Backend currently unreachable',
      detail: `Failed to reach CloudVPS backend at ${BACKEND_URL} (${err.message}). If using Render free tier, the instance may take up to a minute to wake up.`,
      status: 502,
    });
  }
});

// Static assets
app.use(express.static(path.join(__dirname), { index: false }));

// Serve index.html for all other routes
app.use((req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`[CloudVPS] Server running on http://0.0.0.0:${PORT}`);
  console.log(`[CloudVPS] Proxying /api to ${BACKEND_URL}`);
});

