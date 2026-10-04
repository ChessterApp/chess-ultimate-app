import { NextRequest, NextResponse } from "next/server";

/**
 * Onboarding player-verification proxy.
 *
 * The onboarding username step used to call api.chess.com / lichess.org directly
 * from the browser. Those requests are blocked by the site Content-Security-Policy
 * (connect-src allowlist) and Chess.com additionally 403s requests without a
 * browser User-Agent. Doing the lookup server-side fixes both and lets us
 * distinguish a genuine "not found" (upstream 404) from a transient network /
 * upstream failure.
 *
 * GET /api/onboarding/verify-player?platform=chessdotcom|lichess&username=<name>
 *
 * Responses:
 *  200 { found: true, username, rating, ratingType }  — player exists
 *  200 { found: false }                               — genuine not found (404)
 *  400 { error: "missing_username" }                  — bad request
 *  502 { error: "upstream_error" | "network_error" }  — transient failure
 */

const BROWSER_UA =
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

type RatingEntry = [string, number];

function bestRating(entries: RatingEntry[]): RatingEntry | undefined {
  return entries
    .filter((e): e is RatingEntry => typeof e[1] === "number" && e[1] > 0)
    .sort((a, b) => b[1] - a[1])[0];
}

async function upstreamFetch(url: string): Promise<Response> {
  return fetch(url, {
    method: "GET",
    headers: { Accept: "application/json", "User-Agent": BROWSER_UA },
    signal: AbortSignal.timeout(10000),
  });
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const platform = searchParams.get("platform") || "chessdotcom";
  const username = (searchParams.get("username") || "").trim();

  if (!username) {
    return NextResponse.json({ error: "missing_username" }, { status: 400 });
  }

  try {
    if (platform === "lichess") {
      const res = await upstreamFetch(
        `https://lichess.org/api/user/${encodeURIComponent(username)}`
      );
      if (res.status === 404) {
        return NextResponse.json({ found: false }, { status: 200 });
      }
      if (!res.ok) {
        return NextResponse.json({ error: "upstream_error" }, { status: 502 });
      }
      const data = await res.json();
      // Lichess returns 200 with closed/disabled flags for dead accounts.
      if (data?.closed || data?.disabled) {
        return NextResponse.json({ found: false }, { status: 200 });
      }
      const best = bestRating([
        ["Rapid", data?.perfs?.rapid?.rating],
        ["Blitz", data?.perfs?.blitz?.rating],
        ["Bullet", data?.perfs?.bullet?.rating],
        ["Classical", data?.perfs?.classical?.rating],
        ["Correspondence", data?.perfs?.correspondence?.rating],
      ]);
      return NextResponse.json(
        {
          found: true,
          username: data?.username || username,
          rating: best ? best[1] : 0,
          ratingType: best ? best[0] : "",
        },
        { status: 200 }
      );
    }

    // Default: Chess.com
    const lower = username.toLowerCase();
    const playerRes = await upstreamFetch(
      `https://api.chess.com/pub/player/${encodeURIComponent(lower)}`
    );
    if (playerRes.status === 404) {
      return NextResponse.json({ found: false }, { status: 200 });
    }
    if (!playerRes.ok) {
      return NextResponse.json({ error: "upstream_error" }, { status: 502 });
    }

    // Player exists. Rating is best-effort — never fail the lookup over it.
    let rating = 0;
    let ratingType = "";
    try {
      const statsRes = await upstreamFetch(
        `https://api.chess.com/pub/player/${encodeURIComponent(lower)}/stats`
      );
      if (statsRes.ok) {
        const stats = await statsRes.json();
        const best = bestRating([
          ["Rapid", stats?.chess_rapid?.last?.rating],
          ["Blitz", stats?.chess_blitz?.last?.rating],
          ["Bullet", stats?.chess_bullet?.last?.rating],
          ["Daily", stats?.chess_daily?.last?.rating],
        ]);
        if (best) {
          rating = best[1];
          ratingType = best[0];
        }
      }
    } catch {
      // ignore — rating stays 0
    }

    return NextResponse.json(
      { found: true, username: lower, rating, ratingType },
      { status: 200 }
    );
  } catch {
    return NextResponse.json({ error: "network_error" }, { status: 502 });
  }
}
