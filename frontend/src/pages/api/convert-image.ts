import type { NextApiRequest, NextApiResponse } from 'next';
import { checkVisionRateLimit, CONVERT_IMAGE_LIMITS } from '@/lib/vision-rate-limit';

interface ConvertImageResponse {
  fen?: string;
  /** False when the photo does not show whose move it is (White is set then). */
  turn_known?: boolean;
  error?: string;
  raw_response?: string;
}

export const config = {
  api: {
    bodyParser: {
      sizeLimit: '10mb', // Allow larger images
    },
  },
  // The vision call takes 7–22 s (minimal reasoning; up to 60 s with the
  // model's default) — longer than a default function budget.
  maxDuration: 60,
};

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse<ConvertImageResponse>
) {
  // Only allow POST requests
  if (req.method !== 'POST') {
    return res.status(405).json({
      error: 'Method not allowed'
    });
  }

  // Paid vision call: budget per signed-in user, tighter budget per anonymous IP.
  const limit = checkVisionRateLimit(req, 'convert-image', CONVERT_IMAGE_LIMITS);
  if (!limit.allowed) {
    res.setHeader('Retry-After', String(limit.retryAfterSeconds));
    return res.status(429).json({ error: 'rate_limited' });
  }

  try {
    const { image } = req.body;

    if (!image) {
      return res.status(400).json({
        error: 'No image provided'
      });
    }

    // Proxy to Flask backend
    // Use INTERNAL_BACKEND_URL for Docker network, fallback to NEXT_PUBLIC_BACKEND_URL or localhost
    const BACKEND_URL = process.env.INTERNAL_BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'https://api.chesster.io';

    const response = await fetch(`${BACKEND_URL}/api/convert-image`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ image }),
    });

    const data = await response.json();

    if (!response.ok) {
      return res.status(response.status).json({
        error: data.error || 'Failed to convert image',
        raw_response: data.raw_response,
      });
    }

    return res.status(200).json({
      fen: data.fen,
      ...(typeof data.turn_known === 'boolean' ? { turn_known: data.turn_known } : {}),
    });

  } catch (error) {
    console.error("Error converting image to FEN:", error);

    return res.status(500).json({
      error: "Failed to analyze the image. Please try again."
    });
  }
}
