// MapLibre + PMTiles. Globalne `maplibregl` i `pmtiles` są używane wyłącznie w createMap,
// dzięki czemu fillColorExpression da się testować w Node.
export const COLORS = {
  noData: "#b0bec5",
  // klasy wg scoreClass: <10, 10–25, 25–45, 45–65, >65
  classes: ["#9e9e9e", "#fff59d", "#fdd835", "#fb8c00", "#d32f2f"],
};
export const CLASS_LABELS = ["brak", "słabo", "średnio", "dobrze", "bardzo dobrze"];
export const FILL_OPACITY = { weak: 0.3, normal: 0.65, noData: 0.5 };

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

export function fillColorExpression(pogoda, species, dayIdx) {
  if (pogoda == null) return stepOn(scoreExpr(species, null), COLORS.classes);
  return [
    "let", "wv", weatherMatch(pogoda, species, dayIdx),
    ["case",
      ["<", ["var", "wv"], 0], COLORS.noData,
      stepOn(scoreExpr(species, ["var", "wv"]), COLORS.classes)],
  ];
}

export function fillOpacityExpression(pogoda, species, dayIdx) {
  const opacities = [FILL_OPACITY.weak, ...Array(4).fill(FILL_OPACITY.normal)];
  if (pogoda == null) return stepOn(scoreExpr(species, null), opacities);
  return [
    "let", "wv", weatherMatch(pogoda, species, dayIdx),
    ["case",
      ["<", ["var", "wv"], 0], FILL_OPACITY.noData,
      stepOn(scoreExpr(species, ["var", "wv"]), opacities)],
  ];
}

export function setView(map, pogoda, species, dayIdx) {
  map.setPaintProperty("lasy-fill", "fill-color", fillColorExpression(pogoda, species, dayIdx));
  map.setPaintProperty("lasy-fill", "fill-opacity", fillOpacityExpression(pogoda, species, dayIdx));
}

export function createMap(container, { center, zoom, onFeatureClick, onMove, pogoda = null, species = "borowik", dayIdx = 0 }) {
  const protocol = new pmtiles.Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);
  const tilesUrl = new URL("data/lasy.pmtiles", location.href).href;

  const map = new maplibregl.Map({
    container,
    center,
    zoom,
    attributionControl: false,
    style: {
      version: 8,
      sources: {
        osm: {
          type: "raster",
          tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
          tileSize: 256,
          maxzoom: 19,
          attribution: "© OpenStreetMap",
        },
        lasy: { type: "vector", url: "pmtiles://" + tilesUrl, minzoom: 8, maxzoom: 14 },
      },
      layers: [
        { id: "osm", type: "raster", source: "osm" },
        {
          id: "lasy-fill", type: "fill", source: "lasy", "source-layer": "lasy",
          paint: {
            "fill-color": fillColorExpression(pogoda, species, dayIdx),
            "fill-opacity": fillOpacityExpression(pogoda, species, dayIdx),
          },
        },
        {
          id: "lasy-line", type: "line", source: "lasy", "source-layer": "lasy", minzoom: 12,
          paint: { "line-color": "#3e2723", "line-width": 0.6, "line-opacity": 0.6 },
        },
      ],
    },
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

  map.on("click", (e) => {
    const f = map.queryRenderedFeatures(e.point, { layers: ["lasy-fill"] })[0];
    if (f && onFeatureClick) onFeatureClick(f.properties, e.lngLat);
  });
  map.on("mouseenter", "lasy-fill", () => (map.getCanvas().style.cursor = "pointer"));
  map.on("mouseleave", "lasy-fill", () => (map.getCanvas().style.cursor = ""));
  if (onMove) map.on("moveend", () => onMove(map));
  return map;
}
