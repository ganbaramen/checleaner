/* Service worker for the hosted Checleaner PWA.
   Two jobs: keep the app usable offline once installed, and receive an image
   shared to it from the Android share sheet (Web Share Target). Bump VERSION
   to force clients onto a new app shell. */
const VERSION = "checleaner-v2";
// Pinned exactly: the app hard-codes the same version, and an unpinned runtime
// could change decode behaviour under a cached model without anything here
// noticing. Only these two files are ever fetched -- verified by watching the
// requests, because ORT picks its wasm by feature detection and precaching the
// wrong name would leave the app quietly online-only.
const ORT = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.17.3/dist/";
const FACE = [ORT + "ort.min.js", ORT + "ort-wasm-simd.wasm"];
const SHELL = ["./", "./index.html", "./manifest.webmanifest",
               "./icon-192.png", "./icon-512.png", "./apple-touch-icon.png",
               "./face_detection_yunet_2023mar.onnx"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then(async (c) => {
    await c.addAll(SHELL);
    // The face runtime is ~10.6 MB and comes from another origin. Fetched with
    // mode "cors" so the response is a real one that can be revalidated, not an
    // opaque blob; and *not* awaited into the install's success, so a CDN
    // hiccup can't stop the app installing -- it just means reorientation waits
    // for the next online launch. Same "graceful absence" contract
    // content_rotation() has always had.
    c.addAll(FACE.map(u => new Request(u, { mode: "cors" }))).catch(() => {});
  }).then(() => self.skipWaiting()));
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

  if (req.method !== "GET") return;
  // The pinned runtime is cross-origin, so it has to be served from the cache
  // explicitly -- the same-origin guard below would hand it to the network and
  // the app would silently stop working offline.
  if (req.url.startsWith(ORT)) {
    e.respondWith(caches.match(req).then(r => r || fetch(req).then(resp => {
      const copy = resp.clone();
      caches.open(VERSION).then(c => c.put(req, copy)).catch(() => {});
      return resp;
    })));
    return;
  }
  if (url.origin !== self.location.origin) return;

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
