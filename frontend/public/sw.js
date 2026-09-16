const CACHE_VERSION = '16';
const CACHE_NAME = 'chesster-v' + CACHE_VERSION;
const STALE_CACHE = 'chesster-stale-v' + CACHE_VERSION;

// Cache TTLs in milliseconds
const EXPLORER_TTL = 5 * 60 * 1000;   // 5 minutes for Lichess Explorer
const CHESSCOM_TTL = 10 * 60 * 1000;  // 10 minutes for Chess.com
const TWIC_TTL = 60 * 60 * 1000;      // 1 hour for TWIC game queries

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_NAME && k !== STALE_CACHE)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// --- Strategy helpers ---

function cacheFirst(event) {
  event.respondWith(
    caches.match(event.request).then((cached) =>
      cached || fetch(event.request).then((response) => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        return response;
      })
    ).catch(() => new Response('', { status: 404 }))
  );
}

function networkFirst(event) {
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Only cache successful responses — never persist 4xx/5xx or empty
        // bodies, which would otherwise get served as stale content offline.
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() =>
        caches.match(event.request).then((cached) =>
          cached || new Response('Offline', { status: 503, statusText: 'Service Unavailable' })
        )
      )
  );
}

function staleWhileRevalidate(event, ttlMs) {
  event.respondWith(
    caches.open(CACHE_NAME).then((cache) =>
      cache.match(event.request).then((cached) => {
        const fetchPromise = fetch(event.request).then((response) => {
          // Store with timestamp header for TTL checking
          const headers = new Headers(response.headers);
          headers.set('sw-cache-time', String(Date.now()));
          const timedResponse = new Response(response.clone().body, {
            status: response.status,
            statusText: response.statusText,
            headers,
          });
          cache.put(event.request, timedResponse);
          return response;
        }).catch(() => {
          // Network failed — return cached or error
          return cached || new Response('Offline', { status: 503 });
        });

        if (cached) {
          // Check if cached response is still fresh
          const cacheTime = Number(cached.headers.get('sw-cache-time') || '0');
          const age = Date.now() - cacheTime;
          if (age < ttlMs) {
            // Still fresh — return cached, revalidate in background
            fetchPromise.catch(() => {});
            return cached;
          }
        }

        // No cache or stale beyond TTL — wait for network
        return fetchPromise;
      })
    )
  );
}

function networkOnly(event) {
  event.respondWith(fetch(event.request));
}

// --- Route matching helpers ---

function isStaticAsset(url) {
  return (
    url.pathname.startsWith('/_next/static/') ||
    url.pathname.startsWith('/static/') ||
    url.pathname.endsWith('.svg') ||
    url.pathname.endsWith('.png') ||
    url.pathname.endsWith('.jpg') ||
    url.pathname.endsWith('.jpeg') ||
    url.pathname.endsWith('.gif') ||
    url.pathname.endsWith('.ico') ||
    url.pathname.endsWith('.webp') ||
    url.pathname.endsWith('.css') ||
    (url.pathname.startsWith('/_next/') && url.pathname.endsWith('.js'))
  );
}

function isExcludedFile(url) {
  return (
    url.pathname.endsWith('.wasm') ||
    url.pathname.endsWith('.mjs') ||
    url.pathname === '/maia-worker.js' ||
    url.pathname.startsWith('/ort/') ||
    url.pathname.startsWith('/static/engine/')
  );
}

// Maia model files (.onnx) — cached cache-first as a second persistent copy
// alongside IndexedDB, so an evicted IndexedDB doesn't force a re-download.
// The filename is version-keyed (…_int8.onnx), so cache-first is always safe.
function isMaiaModel(url) {
  return url.pathname.startsWith('/maia3/') && url.pathname.endsWith('.onnx');
}

function isLichessExplorer(url) {
  return url.pathname.startsWith('/api/explorer/');
}

function isChessComApi(url) {
  return url.pathname.startsWith('/api/chesscom/');
}

function isTwicGames(url) {
  return url.pathname === '/api/openings/games/by-position';
}

function isAiChatStream(url) {
  return url.pathname.startsWith('/api/chat/stream');
}

function isFlaskApi(url) {
  return url.pathname.startsWith('/api/');
}

// Next.js RSC payload fetches for client-side navigations. These are plain
// GET fetches (mode !== 'navigate') that carry an `RSC` header or a `_rsc`
// search param. Serving them Cache-First permanently pins returning users to
// a pre-update page, so they must always go Network-First.
function isRscRequest(request, url) {
  return request.headers.get('RSC') === '1' || url.searchParams.has('_rsc');
}

// --- Main fetch handler ---

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  // Never intercept worker scripts, WASM, or ORT runtime —
  // these need exact headers (CORP) for cross-origin isolation.
  if (isExcludedFile(url)) return;

  // 0. Maia model (.onnx) → Cache-First. The cached Response keeps its CORP
  //    header, so cross-origin isolation still holds. Immutable, version-keyed.
  if (isMaiaModel(url)) {
    cacheFirst(event);
    return;
  }

  // 1. AI chat streaming → Network-Only (real-time SSE)
  if (isAiChatStream(url)) {
    networkOnly(event);
    return;
  }

  // 2. Lichess Explorer API → Stale-While-Revalidate (5min)
  if (isLichessExplorer(url)) {
    staleWhileRevalidate(event, EXPLORER_TTL);
    return;
  }

  // 3. Chess.com API → Stale-While-Revalidate (10min)
  if (isChessComApi(url)) {
    staleWhileRevalidate(event, CHESSCOM_TTL);
    return;
  }

  // 4. TWIC game queries → Stale-While-Revalidate (1h). Individual games are
  //    immutable, but query results are not: the weekly TWIC import adds new
  //    games to existing positions. Cache-First here served June results in
  //    July until users cleared site data.
  if (isTwicGames(url)) {
    staleWhileRevalidate(event, TWIC_TTL);
    return;
  }

  // 5. Other Flask backend API → Network-First (PowerSync handles most)
  if (isFlaskApi(url)) {
    networkFirst(event);
    return;
  }

  // 6. Navigation → Network-First
  if (event.request.mode === 'navigate') {
    networkFirst(event);
    return;
  }

  // 6b. RSC payload fetches (client-side navigations) → Network-First. Cache-First
  //     here served returning students a permanently stale homepage.
  if (isRscRequest(event.request, url)) {
    networkFirst(event);
    return;
  }

  // 7. Static assets (.js, .css, images, pieces SVG) → Cache-First (immutable,
  //    content-hashed). This is the ONLY Cache-First path for page content.
  if (isStaticAsset(url)) {
    cacheFirst(event);
    return;
  }

  // 8. Everything else → Network-First (fall back to cache when offline). Was
  //    Cache-First, which pinned returning users to stale HTML/RSC payloads.
  networkFirst(event);
});
