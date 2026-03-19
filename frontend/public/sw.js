const CACHE_NAME = 'chesster-v4';
const SHELL_ASSETS = [
  '/',
  '/dashboard',
  '/static/images/chesster-logo.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;

  // Network-first for API calls
  if (event.request.url.includes('/api/')) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          return response;
        })
        .catch(() =>
          caches.match(event.request).then((cached) =>
            cached || new Response('Offline', { status: 503, statusText: 'Service Unavailable' })
          )
        )
    );
    return;
  }

  // Stale-while-revalidate for navigation (HTML pages)
  // Pattern: serve cached version immediately, fetch fresh in background, update cache
  if (event.request.mode === 'navigate') {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        const fetchPromise = fetch(event.request).then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          return response;
        }).catch(() => null); // Ignore fetch errors in background update

        // Return cached immediately if available, otherwise wait for network
        // If cached exists, fetchPromise runs in background to update cache
        return cached || fetchPromise;
      })
    );
    return;
  }

  // Network-first for Next.js build assets (content-hashed, must bust on deploy)
  if (event.request.url.includes('/_next/')) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          return response;
        })
        .catch(() =>
          caches.match(event.request).then((cached) =>
            cached || new Response('Offline', { status: 503, statusText: 'Service Unavailable' })
          )
        )
    );
    return;
  }

  // Cache-first for other static assets
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
