import { BASEMAP_KEYS } from "./hash.js";
import { SPECIES, ALL, wetGammaFor } from "./data.js";

// MapLibre + PMTiles. Globalne `maplibregl` i `pmtiles` są używane wyłącznie w createMap,
// dzięki czemu fillColorExpression da się testować w Node.
export const COLORS = {
  noData: "#b0bec5",
  reserve: "#757575",
  // klasy wg scoreClass: <10, 10–25, 25–45, 45–65, >65
  classes: ["#9e9e9e", "#fff59d", "#fdd835", "#fb8c00", "#d32f2f"],
};
export const CLASS_LABELS = ["brak", "słabo", "średnio", "dobrze", "bardzo dobrze"];
export const FILL_OPACITY = { weak: 0.3, normal: 0.65, noData: 0.5, reserve: 0.5 };

// Progi dla całkowitego wyniku; scoreClass: s <= 65 → "dobrze", więc klasa 4 zaczyna się od 66.
const STEPS = [10, 25, 45, 66];

const hExpr = (species) => ["to-number", ["get", "h_" + species], 0];

// Mnożnik pogody wydzielenia (−1 = brak pogody w komórce), z korektą o wilgotność miejsca (spec L,
// ten sam wzór co adjustW w data.js): w_eff = min(1, w · m^(γ−1)), γ = G^(1 − 2·wet/100), G = wet_gamma gatunku,
// m = moist (spec M), a w starszym pliku rain; brak atrybutu wet → 50 (γ = 1; coalesce, bo to-number(null)
// w MapLibre daje 0), brak m → bez korekty.
function weatherMatch(pogoda, species, dayIdx) {
  const args = [];
  for (const [cell, sp] of Object.entries(pogoda.cells ?? {})) {
    const w = sp?.[species]?.w?.[dayIdx];
    if (w == null) continue;
    const m = sp[species].moist?.[dayIdx] ?? sp[species].rain?.[dayIdx];
    args.push(cell, ["literal", [w, m == null ? 0 : m]]);
  }
  // match wymaga co najmniej jednej pary; bez niej wszystko jest „brak danych”
  if (args.length === 0) return -1;
  const w = ["at", 0, ["var", "wr"]];
  const rain = ["at", 1, ["var", "wr"]];
  const gamma = ["^", wetGammaFor(species), ["-", 1, ["/", ["to-number", ["coalesce", ["get", "wet"], 50]], 50]]];
  return ["let", "wr", ["match", ["get", "cell"], ...args, ["literal", [-1, 0]]],
    ["case",
      ["<", w, 0], -1,
      [">", rain, 0], ["min", 1, ["*", w, ["^", rain, ["-", gamma, 1]]]],
      w]];
}

// Wyrażenie wyniku (0–100) dla wydzielenia; gdy brak pogody → samo h.
function scoreExpr(species, wvVar) {
  return wvVar ? ["round", ["*", hExpr(species), wvVar]] : hExpr(species);
}

const stepOn = (input, values) => {
  const out = ["step", input, values[0]];
  STEPS.forEach((t, i) => out.push(t, values[i + 1]));
  return out;
};

const reserveFirst = (reserveValue, base) => ["case", ["has", "rez"], reserveValue, base];

// Wybór -> lista kluczy: tablica bez zmian, "all" -> wszystkie gatunki, inny napis -> [klucz].
const keysOf = (sel) => (Array.isArray(sel) ? sel : sel === ALL ? SPECIES.map((s) => s.key) : [sel]);

// Tryb wielu gatunków (wszystkie lub grupa): max po kluczach; gatunek bez pogody w komórce daje -1.
const multiHExpr = (keys) => ["max", ...keys.map(hExpr)];
const multiSpeciesExpr = (pogoda, keys, dayIdx) => ["max", ...keys.map((k) => ["let", "wv", weatherMatch(pogoda, k, dayIdx),
  ["case", ["<", ["var", "wv"], 0], -1, scoreExpr(k, ["var", "wv"])]])];

function multiExpression(pogoda, keys, dayIdx, noData, values) {
  if (pogoda == null) return reserveFirst(values.reserve, stepOn(multiHExpr(keys), values.steps));
  return reserveFirst(values.reserve, ["let", "sc", multiSpeciesExpr(pogoda, keys, dayIdx),
    ["case", ["<", ["var", "sc"], 0], noData, stepOn(["var", "sc"], values.steps)]]);
}

// sel: klucz gatunku, "all" albo lista kluczy (grupa).
export function fillColorExpression(pogoda, sel, dayIdx) {
  const keys = keysOf(sel);
  if (keys.length > 1) return multiExpression(pogoda, keys, dayIdx, COLORS.noData, { reserve: COLORS.reserve, steps: COLORS.classes });
  const species = keys[0];
  if (pogoda == null) return reserveFirst(COLORS.reserve, stepOn(scoreExpr(species, null), COLORS.classes));
  return reserveFirst(COLORS.reserve, [
    "let", "wv", weatherMatch(pogoda, species, dayIdx),
    ["case",
      ["<", ["var", "wv"], 0], COLORS.noData,
      stepOn(scoreExpr(species, ["var", "wv"]), COLORS.classes)],
  ]);
}

export function fillOpacityExpression(pogoda, sel, dayIdx) {
  const opacities = [FILL_OPACITY.weak, ...Array(4).fill(FILL_OPACITY.normal)];
  const keys = keysOf(sel);
  if (keys.length > 1) return multiExpression(pogoda, keys, dayIdx, FILL_OPACITY.noData, { reserve: FILL_OPACITY.reserve, steps: opacities });
  const species = keys[0];
  if (pogoda == null) return reserveFirst(FILL_OPACITY.reserve, stepOn(scoreExpr(species, null), opacities));
  return reserveFirst(FILL_OPACITY.reserve, [
    "let", "wv", weatherMatch(pogoda, species, dayIdx),
    ["case",
      ["<", ["var", "wv"], 0], FILL_OPACITY.noData,
      stepOn(scoreExpr(species, ["var", "wv"]), opacities)],
  ]);
}

// Wzór kreskowania rezerwatów: ukośne linie #424242 na przezroczystym tle (RGBA).
export function hatchPattern(size = 8) {
  const data = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const on = (x + y) % size === 0 || (x + y) % size === 1;
      if (!on) continue;
      const i = (y * size + x) * 4;
      data[i] = 0x42; data[i + 1] = 0x42; data[i + 2] = 0x42; data[i + 3] = 255;
    }
  }
  return { width: size, height: size, data };
}

// Ikona parkingu: biały kwadrat z zaokrąglonymi rogami i granatowym „P”.
export function parkingIcon(size = 24) {
  const data = new Uint8Array(size * size * 4);
  const r = 5; // promień zaokrąglenia rogów
  const white = [255, 255, 255];
  const blue = [0x1a, 0x23, 0x7e];
  const corners = [[0, 0], [size - 1, 0], [0, size - 1], [size - 1, size - 1]];
  function cornerDist(x, y) {
    let best = Infinity;
    for (const [cx, cy] of corners) {
      const dx = x - cx;
      const dy = y - cy;
      const d = Math.sqrt(dx * dx + dy * dy);
      if (d < best) best = d;
    }
    return best;
  }
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const i = (y * size + x) * 4;
      // Zaokrąglenie rogów — piksele bliżej niż r od rogu są przezroczyste.
      if (cornerDist(x, y) < r) {
        data[i + 3] = 0;
        continue;
      }
      const [R, G, B] = parkingPixel(x, y, size) ? blue : white;
      data[i] = R; data[i + 1] = G; data[i + 2] = B; data[i + 3] = 255;
    }
  }
  return { width: size, height: size, data };
}

function parkingPixel(x, y, size) {
  // Litera „P” na środku ikony (szer. 8, wys. 13, grubość 2).
  const left = Math.floor((size - 8) / 2); // 8
  const top = Math.floor((size - 13) / 2); // 5
  const rx = x - left;
  const ry = y - top;
  if (rx < 0 || rx >= 8 || ry < 0 || ry >= 13) return false;
  // Pionowa kreska po lewej.
  if (rx < 2) return true;
  // Górna belka.
  if (ry < 2) return true;
  // Środkowa belka.
  if (ry >= 5 && ry < 7) return true;
  // Prawa krawędź górnej pętli.
  if (rx >= 6 && ry < 7) return true;
  return false;
}

const WMS_QUERY =
  "?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=Raster&STYLES=&CRS=EPSG:3857" +
  "&BBOX={bbox-epsg-3857}&WIDTH=256&HEIGHT=256&FORMAT=image/png";

export const BASEMAPS = {
  osm: {
    tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
    attribution: "© OpenStreetMap",
    maxzoom: 19,
  },
  orto: {
    tiles: ["https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/StandardResolution" + WMS_QUERY],
    attribution: "Ortofotomapa: GUGiK (geoportal.gov.pl)",
    maxzoom: 19,
  },
  topo: {
    tiles: ["https://mapy.geoportal.gov.pl/wss/service/img/guest/TOPO/MapServer/WMSServer" + WMS_QUERY],
    attribution: "Mapa topograficzna: GUGiK (geoportal.gov.pl)",
    maxzoom: 17,
  },
};

export function lineColor(basemap) {
  return basemap === "orto" ? { color: "#ffffff", opacity: 0.7 } : { color: "#3e2723", opacity: 0.6 };
}

export function setBasemap(map, key) {
  for (const k of BASEMAP_KEYS) map.setLayoutProperty("base-" + k, "visibility", k === key ? "visible" : "none");
  if (!map.getLayer("lasy-line")) return; // warstwy lasów jeszcze niedodane
  const { color, opacity } = lineColor(key);
  map.setPaintProperty("lasy-line", "line-color", color);
  map.setPaintProperty("lasy-line", "line-opacity", opacity);
}

export function setView(map, pogoda, species, dayIdx) {
  if (!map.getLayer("lasy-fill")) return;
  map.setPaintProperty("lasy-fill", "fill-color", fillColorExpression(pogoda, species, dayIdx));
  map.setPaintProperty("lasy-fill", "fill-opacity", fillOpacityExpression(pogoda, species, dayIdx));
}

// Warstwy lasów i rezerwatów z PMTiles; dodawane po załadowaniu stylu i manifestu (podkład jest od razu).
// pmtilesUrl: względny (data/…) lub pełny URL bucketu; PMTiles pobiera zakresy (Range) przez CORS.
export function addForestLayers(map, pmtilesUrl, { pogoda = null, species = "borowik", dayIdx = 0, basemap = "osm" } = {}) {
  const tilesUrl = new URL(pmtilesUrl, globalThis.location?.href).href;
  const lc = lineColor(basemap);
  map.addSource("lasy", { type: "vector", url: "pmtiles://" + tilesUrl, minzoom: 8, maxzoom: 14 });
  map.addImage("hatch", hatchPattern());
  map.addImage("parking", parkingIcon());
  const layers = [
    {
      id: "lasy-fill", type: "fill", source: "lasy", "source-layer": "lasy",
      paint: {
        "fill-color": fillColorExpression(pogoda, species, dayIdx),
        "fill-opacity": fillOpacityExpression(pogoda, species, dayIdx),
      },
    },
    {
      id: "lasy-rez-hatch", type: "fill", source: "lasy", "source-layer": "lasy",
      filter: ["has", "rez"],
      paint: { "fill-pattern": "hatch" },
    },
    {
      id: "lasy-line", type: "line", source: "lasy", "source-layer": "lasy", minzoom: 12,
      paint: { "line-color": lc.color, "line-width": 0.6, "line-opacity": lc.opacity },
    },
    {
      id: "rezerwaty-fill", type: "fill", source: "lasy", "source-layer": "rezerwaty",
      paint: { "fill-color": "#6a1b9a", "fill-opacity": 0.08 },
    },
    {
      id: "rezerwaty-line", type: "line", source: "lasy", "source-layer": "rezerwaty",
      paint: { "line-color": "#6a1b9a", "line-width": 1.5 },
    },
    {
      id: "parkingi", type: "symbol", source: "lasy", "source-layer": "parkingi", minzoom: 11,
      layout: { "icon-image": "parking", "icon-allow-overlap": true },
    },
  ];
  for (const l of layers) map.addLayer(l);
}

export function createMap(container, { center, zoom, onFeatureClick, onReserveClick, onParkingClick, onMove, basemap = "osm" }) {
  const protocol = new pmtiles.Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);

  const baseSources = {};
  const baseLayers = [];
  for (const k of BASEMAP_KEYS) {
    const b = BASEMAPS[k];
    baseSources["base-" + k] = { type: "raster", tiles: b.tiles, tileSize: 256, maxzoom: b.maxzoom, attribution: b.attribution };
    baseLayers.push({
      id: "base-" + k, type: "raster", source: "base-" + k,
      layout: { visibility: k === basemap ? "visible" : "none" },
    });
  }

  const map = new maplibregl.Map({
    container,
    center,
    zoom,
    attributionControl: false,
    style: { version: 8, sources: baseSources, layers: baseLayers },
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

  map.on("click", (e) => {
    if (!map.getLayer("lasy-fill")) return;
    const p = map.queryRenderedFeatures(e.point, { layers: ["parkingi"] })[0];
    if (p && onParkingClick) {
      onParkingClick(p.properties, e.lngLat);
      return;
    }
    const f = map.queryRenderedFeatures(e.point, { layers: ["lasy-fill"] })[0];
    if (f) {
      if (onFeatureClick) onFeatureClick(f.properties, e.lngLat);
      return;
    }
    const r = map.queryRenderedFeatures(e.point, { layers: ["rezerwaty-fill"] })[0];
    if (r && onReserveClick) onReserveClick(r.properties?.name, e.lngLat);
  });
  map.on("mouseenter", "lasy-fill", () => (map.getCanvas().style.cursor = "pointer"));
  map.on("mouseleave", "lasy-fill", () => (map.getCanvas().style.cursor = ""));
  map.on("mouseenter", "rezerwaty-fill", () => (map.getCanvas().style.cursor = "pointer"));
  map.on("mouseleave", "rezerwaty-fill", () => (map.getCanvas().style.cursor = ""));
  map.on("mouseenter", "parkingi", () => (map.getCanvas().style.cursor = "pointer"));
  map.on("mouseleave", "parkingi", () => (map.getCanvas().style.cursor = ""));
  if (onMove) map.on("moveend", () => onMove(map));
  return map;
}
