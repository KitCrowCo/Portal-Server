const CACHE = 'portal-v0.1';
const PRECACHE = ['/', '/static/icon-192.png', '/static/icon-512.png'];

self.addEventListener('install', e => {
    e.waitUntil(
        caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', e => {
    // Clear old caches on version bump
    e.waitUntil(
        caches.keys()
            .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
            .then(() => clients.claim())
    );
});

self.addEventListener('fetch', e => {
    // Network-first for API/HTMX calls, cache-first for static assets
    const url = new URL(e.request.url);
    if (url.pathname.startsWith('/static/')) {
        e.respondWith(
            caches.match(e.request).then(cached => cached || fetch(e.request).then(res => {
                const clone = res.clone();
                caches.open(CACHE).then(c => c.put(e.request, clone));
                return res;
            }))
        );
    } else {
        // Network first - HTMX/API calls must always be fresh
        e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    }
});

self.addEventListener('push', e => {
    const data = e.data ? e.data.json() : {title: 'Portal', body: 'Notification'};
    e.waitUntil(self.registration.showNotification(data.title, {
        body: data.body,
        icon: '/static/icon-512.png'
    }));
});
