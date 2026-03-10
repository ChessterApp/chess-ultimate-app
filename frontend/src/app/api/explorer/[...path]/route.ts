import { NextRequest, NextResponse } from 'next/server';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    // Extract path segments (e.g., ['masters'] or ['lichess'])
    const resolvedParams = await params;
    const pathSegments = resolvedParams.path;

    if (!pathSegments || pathSegments.length === 0) {
      return NextResponse.json(
        { error: 'Invalid path' },
        { status: 400 }
      );
    }

    // Build the target URL
    const path = pathSegments.join('/');
    const searchParams = request.nextUrl.searchParams;
    const queryString = searchParams.toString();

    const targetUrl = `https://explorer.lichess.ovh/${path}${queryString ? `?${queryString}` : ''}`;

    // Forward the request to Lichess Explorer with browser-like headers
    const response = await fetch(targetUrl, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Referer': 'https://lichess.org/',
        'Origin': 'https://lichess.org',
      },
    });

    if (!response.ok) {
      // Return empty valid response structure instead of error
      return NextResponse.json({
        white: 0,
        draws: 0,
        black: 0,
        moves: [],
        topGames: [],
        opening: null
      }, {
        status: 200,
        headers: {
          'Cache-Control': 'public, max-age=60', // Cache for 1 minute
        },
      });
    }

    const data = await response.json();

    // Return the data with appropriate headers
    return NextResponse.json(data, {
      status: 200,
      headers: {
        'Cache-Control': 'public, max-age=300', // Cache for 5 minutes
      },
    });
  } catch (error) {
    // Return empty valid response structure instead of error
    return NextResponse.json({
      white: 0,
      draws: 0,
      black: 0,
      moves: [],
      topGames: [],
      opening: null
    }, {
      status: 200,
      headers: {
        'Cache-Control': 'public, max-age=60', // Cache for 1 minute
      },
    });
  }
}
