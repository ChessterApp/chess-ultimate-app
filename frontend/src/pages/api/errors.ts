import type { NextApiRequest, NextApiResponse } from 'next';
import fs from 'fs';
import path from 'path';

const LOG_DIR = path.join(process.cwd(), 'logs');
const MAX_LOG_SIZE = 10 * 1024 * 1024; // 10MB — rotate after this

function getLogPath(): string {
  const date = new Date().toISOString().split('T')[0];
  return path.join(LOG_DIR, `errors-${date}.log`);
}

function ensureLogDir() {
  if (!fs.existsSync(LOG_DIR)) {
    fs.mkdirSync(LOG_DIR, { recursive: true });
  }
}

function rotateIfNeeded(logPath: string) {
  try {
    const stats = fs.statSync(logPath);
    if (stats.size > MAX_LOG_SIZE) {
      fs.renameSync(logPath, logPath.replace('.log', `-${Date.now()}.log`));
    }
  } catch {
    // File doesn't exist yet — fine
  }
}

export default function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { errors } = req.body;
    if (!Array.isArray(errors) || errors.length === 0) {
      return res.status(400).json({ error: 'No errors provided' });
    }

    ensureLogDir();
    const logPath = getLogPath();
    rotateIfNeeded(logPath);

    const lines = errors
      .slice(0, 20) // max 20 per request
      .map((err: Record<string, unknown>) => JSON.stringify({
        ...err,
        receivedAt: new Date().toISOString(),
        ip: req.headers['x-forwarded-for'] || req.socket.remoteAddress,
      }))
      .join('\n') + '\n';

    fs.appendFileSync(logPath, lines);

    return res.status(200).json({ ok: true, logged: errors.length });
  } catch (err) {
    console.error('Error logging failed:', err);
    return res.status(500).json({ error: 'Logging failed' });
  }
}
