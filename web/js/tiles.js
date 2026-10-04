import { getJson } from "./config.js";

// Centroidy w kafelkach 0,5°: centroidy/index.json = {tile, species, extra?, tiles}, centroidy/<lat0>_<lon0>.json = {rows}.

const DEFAULT_TILE = 0.5;
const rad = (d) => (d * Math.PI) / 180;

const fmt = (v) => (Object.is(v, -0) ? 0 : v).toFixed(1);
const cellOf = (v, t) => Math.floor(v / t);

export function tileKey(lat, lon, tile = DEFAULT_TILE) {
  return `${fmt(cellOf(lat, tile) * tile)}_${fmt(cellOf(lon, tile) * tile)}`;
}

function keysInRange(latMin, latMax, lonMin, lonMax, index) {
  if (!index?.tiles?.length) return [];
  const t = index.tile ?? DEFAULT_TILE;
  const have = new Set(index.tiles);
  const out = [];
  const lo = Math.max(lonMin, -180);
  const hi = Math.min(lonMax, 180);
  for (let a = cellOf(latMin, t); a <= cellOf(latMax, t); a++) {
    for (let o = cellOf(lo, t); o <= cellOf(hi, t); o++) {
      const k = `${fmt(a * t)}_${fmt(o * t)}`;
      if (have.has(k)) out.push(k);
    }
  }
  return out;
}

// Kafelki z indeksu przecinające bbox promienia: lat ±r/111, lon ±r/(111·cos lat) — jak filtr w topN.
export function tilesForRadius(origin, radiusKm, index) {
  const dLat = radiusKm / 111;
  const dLon = radiusKm / (111 * Math.max(Math.cos(rad(origin.lat)), 0.01));
  return keysInRange(origin.lat - dLat, origin.lat + dLat, origin.lon - dLon, origin.lon + dLon, index);
}

// Kafelek zawierający punkt i 8 sąsiednich (tylko obecne w indeksie).
export function tilesAround(lat, lon, index) {
  const t = index?.tile ?? DEFAULT_TILE;
  return keysInRange(lat - t, lat + t, lon - t, lon + t, index);
}

export const TILE_TIMEOUT_MS = 30000;

// base — katalog kafelków (z końcowym "/"). Cache po kluczu; równoległe żądania tego samego kafelka współdzielą fetch.
// Kafelek z limitem czasu timeoutMs (zawieszony bucket nie blokuje rankingu bez końca); pliki wersji są immutable.
// Nieudany kafelek → pominięty (i usunięty z cache, żeby spróbować ponownie przy następnym rankingu);
// gdy nie uda się żaden z potrzebnych kafelków, rowsNear/findRow odrzucają (ranking pokazuje komunikat błędu).
export function createCentroidStore(fetcher, base, index, { timeoutMs = TILE_TIMEOUT_MS } = {}) {
  const cache = new Map();
  const load = (key) => {
    let p = cache.get(key);
    if (!p) {
      p = (async () => {
        const j = await getJson(fetcher, base + key + ".json", timeoutMs, "default");
        return Array.isArray(j?.rows) ? j.rows : [];
      })().catch((e) => {
        cache.delete(key);
        console.warn("Kafelek centroidów:", e?.message);
        return null;
      });
      cache.set(key, p);
    }
    return p;
  };
  const rowsOf = async (keys) => {
    const parts = await Promise.all(keys.map(load));
    if (parts.length && parts.every((p) => p === null)) throw new Error("nie udało się wczytać kafelków centroidów");
    return parts.filter((p) => p !== null).flat();
  };
  return {
    species: index?.species ?? [],
    extra: index?.extra ?? [],
    rowsNear: (origin, radiusKm) => rowsOf(tilesForRadius(origin, radiusKm, index)),
    // Najpierw kafelek środka, sąsiednie (3×3) dopiero gdy tam go nie ma.
    async findRow(id, lat, lon) {
      const center = tileKey(lat, lon, index?.tile ?? DEFAULT_TILE);
      const all = tilesAround(lat, lon, index);
      const find = (rows) => rows.find((r) => r[0] === id) ?? null;
      if (all.includes(center)) {
        const hit = find((await load(center)) ?? []);
        if (hit) return hit;
      }
      return find(await rowsOf(all.filter((k) => k !== center)));
    },
  };
}
