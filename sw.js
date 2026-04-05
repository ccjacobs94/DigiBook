const CACHE_NAME = 'digibook-cache-v1';
const urlsToCache = [
  '/',
  '/static/manifest.json'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  // Only cache GET requests for our shell
  if (event.request.method !== 'GET') return;

  // Exclude API calls and media files from basic caching to ensure fresh metadata and avoid caching huge audio files in SW.
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/audio/') || url.pathname.startsWith('/cover/')) {
      return;
  }

  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          return response;
        }
        return fetch(event.request);
      })
  );
});
