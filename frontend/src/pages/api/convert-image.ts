import type { NextApiRequest, NextApiResponse } from 'next';

interface ConvertImageResponse {
  fen?: string;
  error?: string;
  raw_response?: string;
}

export const config = {
  api: {
    bodyParser: {
      sizeLimit: '10mb', // Allow larger images
    },
  },
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

  try {
    const { image } = req.body;

    if (!image) {
      return res.status(400).json({
        error: 'No image provided'
      });
    }

    // Proxy to Flask backend
    // Use INTERNAL_BACKEND_URL for Docker network, fallback to NEXT_PUBLIC_BACKEND_URL or localhost
    const BACKEND_URL = process.env.INTERNAL_BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:5001';

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
      fen: data.fen
    });

  } catch (error) {
    console.error("Error converting image to FEN:", error);

    return res.status(500).json({
      error: "Failed to analyze the image. Please try again."
    });
  }
}
