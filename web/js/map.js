import { BASEMAP_KEYS } from "./hash.js";

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

function weatherMatch(pogoda, species, dayIdx) {
  const args = [];
  for (const [cell, sp] of Object.entries(pogoda.cells ?? {})) {
    const w = sp?.[species]?.w?.[dayIdx];
    if (w != null) args.push(cell, w);
  }
  // match wymaga co najmniej jednej pary; bez niej wszystko jest „brak danych”
  if (args.length === 0) return -1;
  return ["match", ["get", "cell"], ...args, -1];
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

export function fillColorExpression(pogoda, species, dayIdx) {
  if (pogoda == null) return reserveFirst(COLORS.reserve, stepOn(scoreExpr(species, null), COLORS.classes));
  return reserveFirst(COLORS.reserve, [
    "let", "wv", weatherMatch(pogoda, species, dayIdx),
    ["case",
      ["<", ["var", "wv"], 0], COLORS.noData,
      stepOn(scoreExpr(species, ["var", "wv"]), COLORS.classes)],
  ]);
}

export function fillOpacityExpression(pogoda, species, dayIdx) {
  const opacities = [FILL_OPACITY.weak, ...Array(4).fill(FILL_OPACITY.normal)];
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
  const { color, opacity } = lineColor(key);
  map.setPaintProperty("lasy-line", "line-color", color);
  map.setPaintProperty("lasy-line", "line-opacity", opacity);
}

export function setView(map, pogoda, species, dayIdx) {
  map.setPaintProperty("lasy-fill", "fill-color", fillColorExpression(pogoda, species, dayIdx));
  map.setPaintProperty("lasy-fill", "fill-opacity", fillOpacityExpression(pogoda, species, dayIdx));
}

export function createMap(container, { center, zoom, onFeatureClick, onReserveClick, onMove, pogoda = null, species = "borowik", dayIdx = 0, basemap = "osm" }) {
  const protocol = new pmtiles.Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);
  const tilesUrl = new URL("data/lasy.pmtiles", location.href).href;
  const lc = lineColor(basemap);

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
    style: {
      version: 8,
      sources: {
        ...baseSources,
        lasy: { type: "vector", url: "pmtiles://" + tilesUrl, minzoom: 8, maxzoom: 14 },
      },
      layers: [
        ...baseLayers,
        {
          id: "lasy-fill", type: "fill", source: "lasy", "source-layer": "lasy",
          paint: {
            "fill-color": fillColorExpression(pogoda, species, dayIdx),
            "fill-opacity": fillOpacityExpression(pogoda, species, dayIdx),
          },
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
      ],
    },
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

  map.on("load", () => {
    map.addImage("hatch", hatchPattern());
    map.addLayer({
      id: "lasy-rez-hatch", type: "fill", source: "lasy", "source-layer": "lasy",
      filter: ["has", "rez"],
      paint: { "fill-pattern": "hatch" },
    }, "lasy-line");
  });

  map.on("click", (e) => {
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
  if (onMove) map.on("moveend", () => onMove(map));
  return map;
}
