const CACHE = 'portal-v0.3';   // a new name clears the older caches when this worker activates
const PRECACHE = ['/', '/static/icon-192.png', '/static/icon-512.png'];

self.addEventListener('install', e => {
    e.waitUntil( caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting()) );
});

self.addEventListener('activate', e => {
    // Clear old caches on version bump
    e.waitUntil(
        caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => clients.claim())
    );
});

self.addEventListener('fetch', e => {
    // Network first for everything, so an updated server is used as soon as it is reachable (cache-first kept old /static/ files in the app until the cache name changed);
    // static files are also kept in the cache, so the app still starts when the server cannot be reached.
    const url = new URL(e.request.url);
    if (e.request.method === 'GET' && url.pathname.startsWith('/static/')) {
        e.respondWith(
            fetch(e.request).then(res => {
                if (res.ok) { const clone = res.clone(); caches.open(CACHE).then(c => c.put(e.request, clone)); }
                return res;
            }).catch(() => caches.match(e.request))
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
