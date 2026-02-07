const fs = require('fs');
const path = require('path');

// Load .env.local file
const envPath = path.join(__dirname, '.env.local');
const envVars = {};

if (fs.existsSync(envPath)) {
  const envContent = fs.readFileSync(envPath, 'utf8');
  envContent.split('\n').forEach(line => {
    line = line.trim();
    if (line && !line.startsWith('#')) {
      const [key, ...valueParts] = line.split('=');
      if (key && valueParts.length > 0) {
        envVars[key.trim()] = valueParts.join('=').trim();
      }
    }
  });
}

module.exports = {
  apps: [{
    name: 'chess-frontend',
    script: '.next/standalone/server.js',
    cwd: '/root/chess-app/frontend',
    env: {
      NODE_ENV: 'production',
      PORT: 3000,
      HOSTNAME: '0.0.0.0',
      ...envVars
    },
    instances: 1,
    exec_mode: 'fork',
    max_memory_restart: '500M'
  }]
}
