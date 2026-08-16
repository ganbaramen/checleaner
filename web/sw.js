/* Service worker for the hosted Checleaner PWA.
   Two jobs: keep the app usable offline once installed, and receive an image
   shared to it from the Android share sheet (Web Share Target). Bump VERSION
   to force clients onto a new app shell. */
const VERSION = "checleaner-v1";
const SHELL = ["./", "./index.html", "./manifest.webmanifest",
               "./icon-192.png", "./icon-512.png", "./apple-touch-icon.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== VERSION && k !== "shared").map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request, url = new URL(req.url);

  // Share sheet: Android POSTs the picked image here. Stash it and bounce to
  // the app with ?shared, which the page picks up on load.
  if (req.method === "POST" && url.pathname.endsWith("/share")) {
    e.respondWith((async () => {
      try {
        const file = (await req.formData()).get("image");
        if (file) {
          const cache = await caches.open("shared");
          await cache.put("shared-image", new Response(file, {
            headers: { "content-type": file.type || "image/jpeg",
                       "x-filename": encodeURIComponent(file.name || "shared.jpg") } }));
        }
      } catch (_) { /* fall through to the app either way */ }
      return Response.redirect("./?shared=1", 303);
    })());
    return;
  }

  if (req.method !== "GET" || url.origin !== self.location.origin) return;

  // Navigations network-first (an online visit picks up a new deploy), cache offline.
  if (req.mode === "navigate") {
    e.respondWith(fetch(req)
      .then(r => { const c = r.clone(); caches.open(VERSION).then(k => k.put("./", c)).catch(() => {}); return r; })
      .catch(() => caches.match("./", { ignoreSearch: true }).then(r => r || caches.match("./index.html"))));
    return;
  }

  // Everything else cache-first.
  e.respondWith(caches.match(req).then(r => r || fetch(req).then(resp => {
    const copy = resp.clone();
    caches.open(VERSION).then(c => c.put(req, copy)).catch(() => {});
    return resp;
  })));
});
