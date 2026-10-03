import { weatherFor, score } from "./data.js";

const R_KM = 6371;
const rad = (d) => (d * Math.PI) / 180;

export function haversineKm(a, b) {
  const dLat = rad(b.lat - a.lat);
  const dLon = rad(b.lon - a.lon);
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * R_KM * Math.asin(Math.sqrt(x));
}

// centroids.rows: [id, lat, lon, cell, h_<species>...] with h columns in centroids.species order
export function topN(centroids, pogoda, species, dayIdx, origin, radiusKm = 20, n = 10) {
  const col = 4 + centroids.species.indexOf(species);
  if (col < 4) return [];
  const out = [];
  for (const row of centroids.rows) {
    const [id, lat, lon, cell] = row;
    const dist = haversineKm(origin, { lat, lon });
    if (dist > radiusKm) continue;
    const wx = weatherFor(pogoda, cell, species, dayIdx);
    if (!wx) continue;
    const s = score(row[col], wx.w);
    if (!s) continue;
    out.push({ id, lat, lon, cell, h: row[col], score: s, distanceKm: Math.round(dist * 10) / 10 });
  }
  out.sort((a, b) => b.score - a.score || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  return out.slice(0, n);
}
