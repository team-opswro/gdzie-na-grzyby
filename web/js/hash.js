import { SPECIES } from "./data.js";

const DEFAULT_SPECIES = "borowik";
const round = (x, d) => Number(x.toFixed(d));

export function parseHash(hash) {
  const p = new URLSearchParams((hash || "").replace(/^#/, ""));
  const s = p.get("s");
  const species = SPECIES.some((x) => x.key === s) ? s : DEFAULT_SPECIES;
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
  return { species, day, zoom, center };
}

export function formatHash({ species, day, zoom, center }) {
  const parts = [`s=${species}`, `d=${day}`];
  if (zoom != null) parts.push(`z=${round(zoom, 2)}`);
  if (center) parts.push(`c=${round(center[1], 5)},${round(center[0], 5)}`);
  return "#" + parts.join("&");
}
