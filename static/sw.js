const CACHE_NAME = "tibok-cache-v5"; // Incremented version to force update
const urlsToCache = [
  "/",
  "/login",
  "/static/manifest.json",
  "/static/logo.png",
  "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap",
  "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"
];

// 1. INSTALL: Cache all critical files immediately
self.addEventListener("install", event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      console.log("Opened cache");
      return cache.addAll(urlsToCache);
    })
  );
});

// 2. ACTIVATE: Clean up old caches to prevent conflicts
self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cache => {
          if (cache !== CACHE_NAME) {
            return caches.delete(cache);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// 3. FETCH: Network-First for API, Cache-First for Pages/Static
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);

  // API calls: Network first (to get fresh data), fall back to nothing (handled by UI)
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request).catch(() => {
        // If offline, just return a generic error or empty json, 
        // the UI handles offline data via localStorage anyway.
        return new Response(JSON.stringify({ offline: true }), { 
            headers: { 'Content-Type': 'application/json' } 
        });
      })
    );
    return;
  }

  // HTML Pages & Static Assets: Cache First, then Network
  event.respondWith(
    caches.match(event.request).then(response => {
      // Return cached file if found
      if (response) {
        return response;
      }
      // Otherwise try network
      return fetch(event.request).catch(() => {
        // If network fails (offline) and not in cache, and it's a navigation, show index
        if (event.request.mode === 'navigate') {
            return caches.match('/');
        }
      });
    })
  );
});