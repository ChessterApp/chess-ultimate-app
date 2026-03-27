import type { NextApiRequest, NextApiResponse } from 'next';

interface ScoresheetMetadata {
  white?: string;
  black?: string;
  event?: string;
  date?: string;
}

interface ConvertScoresheetRequest {
  images: string[];
  metadata?: ScoresheetMetadata;
}

interface MoveCorrection {
  move_number: number;
  original: string;
  corrected: string;
  reason: string;
}

interface ConvertScoresheetResponse {
  pgn?: string;
  moves_total?: number;
  moves_corrected?: number;
  corrections?: MoveCorrection[];
  confidence?: number;
  fen_final?: string;
  error?: string;
}

export const config = {
  api: {
    bodyParser: {
      sizeLimit: '10mb', // Allow multiple scoresheet images
    },
  },
};

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse<ConvertScoresheetResponse>
) {
  // Only allow POST requests
  if (req.method !== 'POST') {
    return res.status(405).json({
      error: 'Method not allowed'
    });
  }

  try {
    const { images, metadata } = req.body as ConvertScoresheetRequest;

    if (!images || !Array.isArray(images) || images.length === 0) {
      return res.status(400).json({
        error: 'No images provided or images is not an array'
      });
    }

    if (images.length > 2) {
      return res.status(400).json({
        error: 'Maximum 2 images allowed'
      });
    }

    // Proxy to Flask backend
    const BACKEND_URL = process.env.INTERNAL_BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'https://api.chesster.io';

    const response = await fetch(`${BACKEND_URL}/api/scoresheet/convert`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ images, metadata }),
    });

    const data = await response.json();

    if (!response.ok) {
      return res.status(response.status).json({
        error: data.error || 'Failed to convert scoresheet',
      });
    }

    return res.status(200).json({
      pgn: data.pgn,
      moves_total: data.moves_total,
      moves_corrected: data.moves_corrected,
      corrections: data.corrections,
      confidence: data.confidence,
      fen_final: data.fen_final,
    });

  } catch (error) {
    console.error("Error converting scoresheet to PGN:", error);

    return res.status(500).json({
      error: "Failed to analyze the scoresheet. Please try again."
    });
  }
}
