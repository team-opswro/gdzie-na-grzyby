import { weatherFor, score, bestFor, ALL } from "./data.js";
import { oddzKey } from "./names.js";

const R_KM = 6371;
const rad = (d) => (d * Math.PI) / 180;

export function haversineKm(a, b) {
  const dLat = rad(b.lat - a.lat);
  const dLon = rad(b.lon - a.lon);
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * R_KM * Math.asin(Math.sqrt(x));
}

const SECTORS = ["płn.", "płn.-wsch.", "wsch.", "płd.-wsch.", "płd.", "płd.-zach.", "zach.", "płn.-zach."];

// Kierunek (8 sektorów po 45°) od origin do point.
export function bearing(origin, point) {
  const dLon = rad(point.lon - origin.lon);
  const y = Math.sin(dLon) * Math.cos(rad(point.lat));
  const x = Math.cos(rad(origin.lat)) * Math.sin(rad(point.lat)) - Math.sin(rad(origin.lat)) * Math.cos(rad(point.lat)) * Math.cos(dLon);
  const az = ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
  return SECTORS[Math.round(az / 45) % 8];
}

// centroids.rows: [id, lat, lon, cell, h_<species>...] with h columns in centroids.species order
// Wynik: grupy po oddziale [{ key, best, count, distanceKm, bearing }].
// sel: klucz gatunku, "all" albo lista kluczy (grupa). Wiele kolumn: wynik wiersza = bestFor po nich,
// a grupa ma dodatkowo `species` (klucz najlepszego). Klucze spoza centroids.species są pomijane.
export function topN(centroids, pogoda, sel, dayIdx, origin, radiusKm = 20, n = 10) {
  const keys = Array.isArray(sel) ? sel : sel === ALL ? centroids.species : [sel];
  const cols = keys.map((k) => [k, 4 + centroids.species.indexOf(k)]).filter(([, c]) => c >= 4);
  if (!cols.length) return [];
  const isAll = cols.length > 1;
  const [species, col] = cols[0];
  const groups = new Map();
  const dLat = radiusKm / 111;
  const dLon = radiusKm / (111 * Math.max(Math.cos(rad(origin.lat)), 0.01));
  for (const row of centroids.rows) {
    const [id, lat, lon, cell] = row;
    if (Math.abs(lat - origin.lat) > dLat || Math.abs(lon - origin.lon) > dLon) continue;
    if (haversineKm(origin, { lat, lon }) > radiusKm) continue;
    let s, h, sp, hBy;
    if (isAll) {
      hBy = {};
      for (const [k, c] of cols) hBy[k] = row[c];
      const b = bestFor(pogoda, cell, hBy, dayIdx);
      if (!b) continue;
      s = b.score; sp = b.species; h = hBy[sp];
    } else {
      const wx = weatherFor(pogoda, cell, species, dayIdx);
      if (!wx) continue;
      s = score(row[col], wx.w); h = row[col];
    }
    if (!s) continue;
    const key = oddzKey(id) ?? id;
    const cand = { id, lat, lon, cell, h, score: s };
    if (isAll) { cand.species = sp; cand.hBy = hBy; }
    const g = groups.get(key);
    if (!g) groups.set(key, { key, best: cand, count: 1 });
    else {
      g.count++;
      if (s > g.best.score || (s === g.best.score && id < g.best.id)) g.best = cand;
    }
  }
  const out = [...groups.values()].map((g) => ({
    ...g,
    ...(isAll ? { species: g.best.species } : {}),
    distanceKm: Math.round(haversineKm(origin, g.best) * 10) / 10,
    bearing: bearing(origin, g.best),
  }));
  out.sort((a, b) => b.best.score - a.best.score || (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
  return out.slice(0, n);
}
