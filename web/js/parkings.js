import { haversineKm } from "./ranking.js";

export const PARKING_ZOOM = 11;
export const PARKING_RADIUS_KM = 1.5;

// Odczyt pól protobuf potrzebnych do punktowej warstwy MVT „parkingi”.
function varint(bytes, pos) {
  let value = 0, shift = 0;
  while (pos.i < bytes.length && shift < 56) {
    const b = bytes[pos.i++];
    value += (b & 127) * 2 ** shift;
    if (b < 128) return value;
    shift += 7;
  }
  throw new Error("Nieprawidłowy kafelek parkingów");
}

function fields(bytes) {
  const out = [], pos = { i: 0 };
  while (pos.i < bytes.length) {
    const tag = varint(bytes, pos), wire = tag % 8;
    let value;
    if (wire === 0) value = varint(bytes, pos);
    else if (wire === 2 || wire === 1 || wire === 5) {
      const length = wire === 2 ? varint(bytes, pos) : wire === 1 ? 8 : 4;
      if (pos.i + length > bytes.length) throw new Error("Niepełny kafelek parkingów");
      value = bytes.subarray(pos.i, pos.i + length);
      pos.i += length;
    } else throw new Error("Nieprawidłowy format kafelka parkingów");
    out.push([Math.floor(tag / 8), value]);
  }
  return out;
}

const text = (bytes) => new TextDecoder().decode(bytes);
const packed = (bytes) => {
  const values = [], pos = { i: 0 };
  while (pos.i < bytes.length) values.push(varint(bytes, pos));
  return values;
};
const signed = (value) => value % 2 ? -(value + 1) / 2 : value / 2;

export function decodeParkings(data, z, x, y) {
  const parkings = [];
  for (const [field, layer] of fields(new Uint8Array(data))) {
    if (field !== 3) continue;
    const entries = fields(layer);
    if (text(entries.find(([n]) => n === 1)?.[1] ?? new Uint8Array()) !== "parkingi") continue;
    const keys = entries.filter(([n]) => n === 3).map(([, b]) => text(b));
    const values = entries.filter(([n]) => n === 4).map(([, b]) => {
      const [n, value] = fields(b)[0] ?? [];
      return n === 1 ? text(value) : value;
    });
    const extent = entries.find(([n]) => n === 5)?.[1] ?? 4096;
    if (!Number.isFinite(extent) || extent <= 0) throw new Error("Nieprawidłowy rozmiar kafelka parkingów");
    for (const [n, feature] of entries) {
      if (n !== 2) continue;
      const f = fields(feature);
      if (f.find(([n]) => n === 3)?.[1] !== 1) continue; // geometria POINT
      const props = {};
      for (const [, b] of f.filter(([n]) => n === 2)) {
        const tags = packed(b);
        for (let i = 0; i + 1 < tags.length; i += 2) props[keys[tags[i]]] = values[tags[i + 1]];
      }
      const geometry = f.find(([n]) => n === 4)?.[1];
      if (!geometry) continue;
      const commands = packed(geometry);
      let px = 0, py = 0;
      for (let i = 0; i < commands.length;) {
        const command = commands[i++], id = command % 8, count = Math.floor(command / 8);
        if (id !== 1 || count === 0 || i + count * 2 > commands.length) throw new Error("Nieprawidłowy punkt parkingu");
        for (let j = 0; j < count; j++) {
          px += signed(commands[i++]); py += signed(commands[i++]);
          const lon = (x + px / extent) / 2 ** z * 360 - 180;
          const lat = Math.atan(Math.sinh(Math.PI * (1 - 2 * (y + py / extent) / 2 ** z))) * 180 / Math.PI;
          parkings.push({ id: String(props.osm ?? `${lon},${lat}`), lat, lon, name: props.name, fee: props.fee });
        }
      }
    }
  }
  return parkings;
}

export function parkingTiles(point, radiusKm = PARKING_RADIUS_KM) {
  const dLat = radiusKm / 111;
  const dLon = radiusKm / (111 * Math.cos(point.lat * Math.PI / 180));
  const n = 2 ** PARKING_ZOOM;
  const tx = (lon) => Math.floor((lon + 180) / 360 * n);
  const ty = (lat) => Math.floor((1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * n);
  const tiles = [];
  for (let x = Math.max(0, tx(point.lon - dLon)); x <= Math.min(n - 1, tx(point.lon + dLon)); x++) {
    for (let y = Math.max(0, ty(point.lat + dLat)); y <= Math.min(n - 1, ty(point.lat - dLat)); y++) tiles.push([PARKING_ZOOM, x, y]);
  }
  return tiles;
}

export function createParkingStore(archive, { timeoutMs = 15000 } = {}) {
  const cache = new Map();
  const load = (tile) => {
    const key = tile.join("/");
    if (!cache.has(key)) {
      const pending = (async () => {
        const ctl = new AbortController();
        let timer;
        try {
          const timeout = new Promise((_, reject) => {
            timer = setTimeout(() => { ctl.abort(); reject(new Error("Przekroczono czas pobierania parkingów")); }, timeoutMs);
          });
          const result = await Promise.race([archive.getZxy(...tile, ctl.signal), timeout]);
          return result ? decodeParkings(result.data, ...tile) : [];
        } finally { clearTimeout(timer); }
      })().catch((error) => { cache.delete(key); throw error; });
      cache.set(key, pending);
    }
    return cache.get(key);
  };
  return {
    async near(point) {
      const groups = await Promise.all(parkingTiles(point).map(load));
      const unique = new Map();
      for (const p of groups.flat()) {
        const distance = haversineKm(point, p);
        if (distance <= PARKING_RADIUS_KM) unique.set(p.id, { ...p, forestDistanceKm: distance });
      }
      return [...unique.values()].sort((a, b) => a.forestDistanceKm - b.forestDistanceKm);
    },
  };
}
