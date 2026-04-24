module.exports = {
  apps: [
    {
      name: "hermes-chess",
      cwd: "/root/hermes-chess",
      script: ".venv/bin/python",
      args: "-m src.server",
      interpreter: "none",
      env: {
        HOME: "/root",
        PATH: "/root/hermes-chess/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        HERMES_HOME: "/root/hermes-chess/profiles/chess-coach",
      },
      max_restarts: 10,
      restart_delay: 5000,
      watch: false,
      log_date_format: "YYYY-MM-DD HH:mm:ss",
    },
  ],
};
