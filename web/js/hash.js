import { SPECIES, ALL } from "./data.js";

export const BASEMAP_KEYS = ["osm", "orto", "topo"];
export const RADII = [5, 10, 20, 40];
const DEFAULT_RADIUS = 20;
const PLACE_RE = /^[0-9A-Za-z-]{1,40}$/;
const DEFAULT_SPECIES = "borowik";
const DEFAULT_BASEMAP = "osm";
const round = (x, d) => Number(x.toFixed(d));

export function parseHash(hash, keys = [...SPECIES.map((x) => x.key), ALL]) {
  const p = new URLSearchParams((hash || "").replace(/^#/, ""));
  const s = p.get("s");
  const species = keys.includes(s) ? s : DEFAULT_SPECIES;
  const d = Number(p.get("d"));
  const day = Number.isInteger(d) && d >= 0 && p.get("d") !== "" ? d : 0;
  const z = p.get("z");
  const zoom = z !== null && z !== "" && Number.isFinite(Number(z)) ? Number(z) : undefined;
  let center;
  const c = p.get("c");
  if (c) {
    const [lat, lon] = c.split(",").map((v) => (v.trim() === "" ? NaN : Number(v)));
    if (Number.isFinite(lat) && Number.isFinite(lon)) center = [lon, lat];
  }
  const b = p.get("b");
  const basemap = BASEMAP_KEYS.includes(b) ? b : DEFAULT_BASEMAP;
  const r = Number(p.get("r"));
  const radius = RADII.includes(r) && p.get("r") !== "" ? r : DEFAULT_RADIUS;
  const w = p.get("w");
  const place = w !== null && PLACE_RE.test(w) ? w : undefined;
  return { species, day, zoom, center, basemap, radius, place };
}

export function formatHash({ species, day, zoom, center, basemap, radius, place, coarse }) {
  const parts = [`s=${species}`, `d=${day}`];
  if (zoom != null) parts.push(`z=${round(zoom, 2)}`);
  if (center) {
    const z = zoom ?? 0;
    const d = coarse || z < 13 ? 3 : z < 15 ? 4 : 5;
    parts.push(`c=${round(center[1], d)},${round(center[0], d)}`);
  }
  if (basemap && basemap !== DEFAULT_BASEMAP) parts.push(`b=${basemap}`);
  if (radius != null && radius !== DEFAULT_RADIUS && RADII.includes(radius)) parts.push(`r=${radius}`);
  if (place && PLACE_RE.test(place)) parts.push(`w=${place}`);
  return "#" + parts.join("&");
}
