module.exports = {
  apps: [
    {
      name: 'chess-backend',
      script: 'app.py',
      interpreter: '/root/chess-app/backend/venv/bin/python',
      cwd: '/root/chess-app/backend',
      instances: 1,
      exec_mode: 'fork',
      autorestart: true,
      watch: false,
      max_restarts: 10,
      min_uptime: '10s',
      exp_backoff_restart_delay: 1000,
      max_memory_restart: '400M',
      kill_timeout: 5000,
      env: {
        FLASK_APP: 'app.py',
        FLASK_ENV: 'production',
        FLASK_DEBUG: '0',
      },
      error_file: '/root/.pm2/logs/chess-backend-error.log',
      out_file: '/root/.pm2/logs/chess-backend-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },
  ],
};
