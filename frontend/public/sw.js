const CACHE_VERSION = '4';
const CACHE_NAME = 'chesster-v' + CACHE_VERSION;

self.addEventListener('install', (event) => {
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

  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  // Network-first for everything important: navigation, API, Next.js assets
  if (
    event.request.mode === 'navigate' ||
    event.request.url.includes('/api/') ||
    event.request.url.includes('/_next/')
  ) {
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

  // Cache-first for other static assets (images, fonts)
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
