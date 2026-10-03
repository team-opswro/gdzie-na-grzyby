"use strict";
// Service worker — klasyczny skrypt (importScripts zamiast modułu, dla szerokiego wsparcia).
importScripts("sw-core.js");

const core = self.SWCore;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(core.SHELL_CACHE)
      .then((cache) => cache.addAll(core.SHELL_FILES))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) => Promise.all(core.staleShellCaches(names).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const strategy = core.strategyFor(event.request.url, event.request.method, self.registration.scope);
  if (strategy === "pass") return;
  event.respondWith(handle(event.request, strategy));
});

async function handle(request, strategy) {
  if (strategy === "network-first") return networkFirst(request);
  if (strategy === "cache-first") return cacheFirst(request);
  if (strategy === "swr") return staleWhileRevalidate(request);
  return fetch(request);
}

// Sieć najpierw; po NETWORK_TIMEOUT_MS bez odpowiedzi — kopia z cache, jeśli jest (inaczej dalej
// czekamy na sieć: pierwsza wizyta na wolnym łączu nie może się nie udać przez limit czasu).
async function networkFirst(request) {
  const cache = await caches.open(core.SHELL_CACHE);
  const network = fetch(request).then((resp) => {
    if (resp.ok) cache.put(request, resp.clone()).catch(() => {});
    return resp;
  });
  const timeout = new Promise((resolve) => setTimeout(() => resolve(null), core.NETWORK_TIMEOUT_MS));
  try {
    const first = await Promise.race([network, timeout]);
    if (first) return first;
    return (await cachedFallback(cache, request)) ?? (await network);
  } catch (e) {
    const cached = await cachedFallback(cache, request);
    if (cached) return cached;
    throw e;
  }
}

async function cachedFallback(cache, request) {
  const cached = await cache.match(request);
  if (cached) return cached;
  // wejście na stronę offline bez wpisu dla tego adresu — prekeszowany index.html
  if (request.mode === "navigate") return (await cache.match("index.html")) ?? null;
  return null;
}

async function cacheFirst(request) {
  const dataCache = await caches.open(core.DATA_CACHE);
  const isVersioned = /\/v\/[^/]+\//.test(new URL(request.url).pathname);
  const cache = isVersioned ? dataCache : await caches.open(core.SHELL_CACHE);

  const range = request.headers.get("Range");
  const key = core.cacheKey(request.url, range);
  const cached = await cache.match(key);
  if (cached) {
    return range ? rebuildRange(cached, range) : cached;
  }

  const resp = await fetch(request.clone());
  if (!resp.ok) return resp;
  if (range && resp.status !== 206) return resp; // serwer zignorował Range — nie zapisujemy całości pod kluczem zakresu

  // Kopia powstaje od razu (Cache API zużywa body zapisywanej odpowiedzi); oryginał wraca do strony.
  const copy = resp.clone();
  if (isVersioned) await pruneOtherBuilds(cache, request.url);
  await trimCache(cache, isVersioned ? core.LIMITS.data : core.SHELL_FILES.length + 100);
  if (range) {
    const contentRange = resp.headers.get("Content-Range");
    if (contentRange) await storeRange(cache, key, copy, contentRange).catch(() => {});
  } else {
    await cache.put(key, copy).catch(() => {});
  }
  return resp;
}

// Pliki /v/<build>/ są niezmienne, ale po publikacji nowego buildu stare wpisy są bezużyteczne.
async function pruneOtherBuilds(cache, url) {
  const build = core.buildOf(url);
  if (!build) return;
  const keys = await cache.keys();
  await Promise.all(keys.filter((k) => {
    const b = core.buildOf(k.url);
    return b && b !== build;
  }).map((k) => cache.delete(k)));
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(core.BASE_CACHE);
  const cached = await cache.match(request);
  const networkPromise = fetch(request.clone())
    .then((resp) => {
      if (resp.ok) {
        const copy = resp.clone(); // przed oddaniem odpowiedzi stronie, która od razu czyta body
        trimCache(cache, core.LIMITS.base).then(() => cache.put(request, copy)).catch(() => {});
      }
      return resp;
    })
    .catch(() => Response.error());
  if (cached) return cached;
  return await networkPromise;
}

async function storeRange(cache, key, response, contentRange) {
  const headers = new Headers(response.headers);
  headers.set("X-Content-Range", contentRange);
  // Cache API nie akceptuje odpowiedzi 206 — zapisujemy jako 200 z oryginalnym nagłówkiem w X-Content-Range.
  await cache.put(key, new Response(response.body, { status: 200, headers }));
}

function rebuildRange(stored, range) {
  const contentRange = stored.headers.get("X-Content-Range");
  if (!contentRange) return stored;
  const headers = new Headers(stored.headers);
  headers.set("Content-Range", contentRange);
  headers.delete("X-Content-Range");
  return new Response(stored.body, { status: 206, statusText: "Partial Content", headers });
}

async function trimCache(cache, limit) {
  const keys = await cache.keys();
  if (keys.length <= limit) return;
  const toDelete = core.trimPlan(keys.map((r) => r.url), limit);
  await Promise.all(
    toDelete.map((url) => {
      const req = keys.find((r) => r.url === url);
      return req ? cache.delete(req) : Promise.resolve();
    }),
  );
}
