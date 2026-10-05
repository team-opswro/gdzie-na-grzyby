import { getJson } from "./config.js";
import { haversineKm } from "./ranking.js";

export const ROUTING_BASE = "https://routing.openstreetmap.de/routed-car";
export const MAX_DRIVE_CANDIDATES = 200;
const BATCH = 10;
const coord = (p) => `${p.lon},${p.lat}`;
const parkingKey = (p) => `${p.id}:${coord(p)}`;

export function driveSettings(hash) {
  const params = new URLSearchParams((hash ?? "").replace(/^#/, ""));
  // domyślnie „w linii prostej”: ranking od razu pokazuje miejsca; dojazd samochodem tylko z t=car lub z wyboru
  const mode = params.get("t") === "car" ? "car" : "air";
  let origin = null;
  if (params.has("o")) {
    const parts = params.get("o").split(",");
    const [lat, lon] = parts.map((x) => x.trim() ? Number(x) : NaN);
    if (parts.length === 2 && Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 85 && Math.abs(lon) <= 180) origin = { lat, lon };
  }
  return { mode, origin };
}

export function drivingUrl(origin, parking) {
  return `https://www.google.com/maps/dir/?api=1&origin=${origin.lat},${origin.lon}&destination=${parking.lat},${parking.lon}&travelmode=driving`;
}

// Odległości to długości najszybszych tras samochodowych, bez danych o korkach.
export function createDrivePlanner(parkings, { fetcher = globalThis.fetch, base = ROUTING_BASE, intervalMs = 1100, timeoutMs = 15000 } = {}) {
  let cacheOrigin = "", lastRequest = 0, queue = Promise.resolve();
  const cache = new Map();
  const table = (origin, destinations, current) => {
    const request = queue.then(async () => {
      if (!current()) return;
      let delay;
      while ((delay = intervalMs + 5 - (Date.now() - lastRequest)) > 0) {
        await new Promise((resolve) => setTimeout(resolve, delay));
      }
      if (!current()) return;
      lastRequest = Date.now();
      const coords = [origin, ...destinations].map(coord).join(";");
      const indexes = destinations.map((_, i) => i + 1).join(";");
      const data = await getJson(fetcher, `${base}/table/v1/driving/${coords}?sources=0&destinations=${indexes}&annotations=distance,duration`, timeoutMs);
      if (data.code !== "Ok" || data.distances?.[0]?.length !== destinations.length || data.durations?.[0]?.length !== destinations.length || data.destinations?.length !== destinations.length) throw new Error("Nieprawidłowa odpowiedź usługi dojazdu");
      if (!Number.isFinite(data.sources?.[0]?.distance) || data.sources[0].distance > 1000) throw new Error("Wybierz punkt wyjazdu bliżej drogi");
      return destinations.map((parking, i) => {
        const meters = data.distances[0][i], seconds = data.durations[0][i];
        const snap = data.destinations[i]?.distance;
        return Number.isFinite(meters) && meters >= 0 && Number.isFinite(seconds) && seconds >= 0 && Number.isFinite(snap) && snap <= 100
          ? { parking, meters, seconds } : null;
      });
    });
    queue = request.catch(() => {});
    return request;
  };

  return {
    async find(candidates, origin, limitKm, { n = 10, current = () => true, progress = () => {} } = {}) {
      const originKey = coord(origin);
      if (originKey !== cacheOrigin) { cacheOrigin = originKey; cache.clear(); }
      const selected = candidates.slice(0, MAX_DRIVE_CANDIDATES), results = [];
      let checked = 0;
      for (let offset = 0; offset < selected.length && results.length < n; offset += BATCH) {
        if (!current()) return { results: [], cancelled: true };
        const batch = selected.slice(offset, offset + BATCH);
        const nearby = await Promise.all(batch.map(async (candidate) => (await parkings.near(candidate.best))
          .filter((p) => haversineKm(origin, p) <= limitKm + 0.1).slice(0, 3)));
        if (!current()) return { results: [], cancelled: true };
        const missing = new Map();
        for (const parking of nearby.flat()) if (!cache.has(parkingKey(parking))) missing.set(parkingKey(parking), parking);
        if (missing.size) {
          const pending = [...missing.values()];
          const routes = await table(origin, pending, current);
          if (!current() || !routes) return { results: [], cancelled: true };
          // Wyniki poprzedniego punktu startu nie mogą trafić do nowego cache.
          if (cacheOrigin === originKey) pending.forEach((parking, i) => cache.set(parkingKey(parking), routes[i]));
        }
        for (let i = 0; i < batch.length && results.length < n; i++) {
          const valid = nearby[i].map((p) => {
            const route = cache.get(parkingKey(p));
            return route ? { ...route, parking: p } : null;
          }).filter((r) => r && r.meters <= limitKm * 1000);
          valid.sort((a, b) => a.meters - b.meters);
          if (valid.length) results.push({ ...batch[i], drive: { ...valid[0], origin } });
        }
        checked += batch.length;
        progress(checked, selected.length);
      }
      return { results, checked, limited: results.length < n && selected.length < candidates.length };
    },
  };
}
