import type { NextApiRequest, NextApiResponse } from 'next';

export default function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { errors } = req.body;
    if (!Array.isArray(errors) || errors.length === 0) {
      return res.status(400).json({ error: 'No errors provided' });
    }

    // Log to stdout (picked up by PM2 logs)
    for (const err of errors.slice(0, 20)) {
      console.error('[CLIENT_ERROR]', JSON.stringify({
        type: err.type,
        message: String(err.message || '').substring(0, 500),
        url: err.url,
        timestamp: err.timestamp,
      }));
    }

    return res.status(200).json({ ok: true, logged: errors.length });
  } catch (err) {
    console.error('Error logging failed:', err);
    return res.status(500).json({ error: 'Logging failed' });
  }
}
