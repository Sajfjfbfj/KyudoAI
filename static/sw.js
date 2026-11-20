// 最小限のService Worker (PWAインストール要件を満たすためのキャッシュ・パススルー)
self.addEventListener('install', (e) => {
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(clients.claim());
});

self.addEventListener('fetch', (e) => {
  // 通常のフェッチを通す
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
