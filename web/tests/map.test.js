import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { fillColorExpression, COLORS, FILL_OPACITY, classFill, NO_DATA_FILL, RESERVE_FILL, rgba, hatchPattern, BASEMAPS, lineColor } from "../js/map.js";
import { BASEMAP_KEYS } from "../js/hash.js";
import { parkingIcon } from "../js/map.js";

const P = JSON.parse(fs.readFileSync(new URL("../../tests/fixtures/pogoda.json", import.meta.url), "utf8"));

test("expression contains match on cell with fallback -1", () => {
  const e = JSON.stringify(fillColorExpression(P, "borowik", 0));
  assert.ok(e.includes('"match"') && e.includes('"cell"') && e.includes("-1"));
});

test("expression without pogoda uses h only", () =>
  assert.ok(!JSON.stringify(fillColorExpression(null, "borowik", 0)).includes('"match"')));

test("noData color is distinct from every class color", () =>
  assert.ok(!COLORS.classes.includes(NO_DATA_FILL)));

test("missing-cell branch yields the noData fill (kolor z kryciem)", () => {
  const c = fillColorExpression(P, "borowik", 0)[3];
  assert.deepEqual(c[3], ["case", ["<", ["var", "sc"], 0], NO_DATA_FILL, c[3][3]]);
  assert.equal(NO_DATA_FILL, rgba(COLORS.noData, FILL_OPACITY.noData));
  assert.notEqual(NO_DATA_FILL, classFill(0));
});

test("rgba i krycie klas: „brak” słabszy niż pozostałe, ale widoczny", () => {
  assert.equal(rgba("#9e9e9e", 0.55), "rgba(158,158,158,0.55)");
  assert.equal(classFill(0), rgba(COLORS.classes[0], FILL_OPACITY.weak));
  assert.equal(classFill(3), rgba(COLORS.classes[3], FILL_OPACITY.normal));
  assert.ok(FILL_OPACITY.weak >= 0.5 && FILL_OPACITY.weak < FILL_OPACITY.normal);
});

test("expression reads h_<species> and uses 5 class colors", () => {
  const e = JSON.stringify(fillColorExpression(P, "rydz", 0));
  assert.ok(e.includes("h_rydz"));
  for (let i = 0; i < COLORS.classes.length; i++) assert.ok(e.includes(classFill(i)));
});

test("reserve branch comes first", () => {
  for (const p of [P, null]) {
    const c = fillColorExpression(p, "borowik", 0);
    assert.deepEqual(c.slice(0, 3), ["case", ["has", "rez"], RESERVE_FILL]);
  }
  assert.ok(!COLORS.classes.includes(COLORS.reserve) && COLORS.reserve !== NO_DATA_FILL);
});
test("hatch pattern is 8x8 RGBA with transparent and opaque pixels", () => {
  const h = hatchPattern();
  assert.equal(h.width, 8); assert.equal(h.data.length, 8 * 8 * 4);
  const alphas = new Set([...h.data].filter((_, i) => i % 4 === 3));
  assert.ok(alphas.has(0) && alphas.has(255));
});
test("basemaps", () => {
  assert.deepEqual(Object.keys(BASEMAPS), BASEMAP_KEYS);
  for (const k of ["orto", "topo"]) {
    const u = BASEMAPS[k].tiles[0];
    assert.ok(u.includes("{bbox-epsg-3857}") && u.includes("CRS=EPSG:3857") && u.includes("LAYERS=Raster"));
  }
  assert.deepEqual(lineColor("orto"), { color: "#ffffff", opacity: 0.7 });
  assert.deepEqual(lineColor("osm"), { color: "#3e2723", opacity: 0.6 });
});

import { SPECIES } from "../js/data.js";
import fs2 from "node:fs";
const V1 = JSON.parse(fs2.readFileSync(new URL("../../tests/fixtures/pogoda_v1.json", import.meta.url), "utf8"));

test("all: reserve outermost, max of per-species expressions with h_ and match", () => {
  const e = fillColorExpression(P, "all", 0);
  assert.deepEqual(e.slice(0, 2), ["case", ["has", "rez"]]);
  const s = JSON.stringify(e);
  assert.ok(s.includes('"max"') && s.includes('"match"'));
  for (const k of SPECIES) assert.ok(s.includes("h_" + k.key));
  // jedno dopasowanie kratki dla wszystkich gatunków (wydajność), nie osobny match na gatunek
  assert.equal(s.split('"match"').length - 1, 1);
});
test("all without pogoda: max of h_*, no match", () => {
  for (const e of [fillColorExpression(null, "all", 0)]) {
    const s = JSON.stringify(e);
    assert.ok(s.includes('"max"') && !s.includes('"match"'));
    for (const k of SPECIES) assert.ok(s.includes("h_" + k.key));
  }
});
test("all with old pogoda_v1 does not throw", () => {
  assert.doesNotThrow(() => { fillColorExpression(V1, "all", 0); fillColorExpression(V1, "all", 3); });
});

import { addForestLayers, setView, setBasemap } from "../js/map.js";

function fakeMap(layers = []) {
  const calls = [];
  const have = new Set(layers);
  return {
    calls,
    getLayer: (id) => (have.has(id) ? { id } : undefined),
    addSource: (id, src) => calls.push(["source", id, src]),
    addImage: (id, img) => calls.push(["image", id, img]),
    addLayer: (l) => { have.add(l.id); calls.push(["layer", l.id, l]); },
    setPaintProperty: (id, k) => calls.push(["paint", id, k]),
    setLayoutProperty: (id, k, v) => calls.push(["layout", id, k, v]),
  };
}

test("addForestLayers: pmtiles source from absolute URL, layers in order", () => {
  const m = fakeMap();
  addForestLayers(m, "https://d.example.pl/v/b1/lasy.pmtiles", { pogoda: P, species: "borowik", dayIdx: 0, basemap: "orto" });
  const src = m.calls.find((c) => c[0] === "source");
  assert.equal(src[1], "lasy");
  assert.equal(src[2].url, "pmtiles://https://d.example.pl/v/b1/lasy.pmtiles");
  assert.deepEqual(m.calls.filter((c) => c[0] === "layer").map((c) => c[1]),
    ["lasy-fill", "lasy-rez-hatch", "lasy-line", "rezerwaty-fill", "rezerwaty-line", "parkingi"]);
  assert.ok(m.calls.some((c) => c[0] === "image" && c[1] === "hatch"));
  assert.ok(m.calls.some((c) => c[0] === "image" && c[1] === "parking"));
});

test("setView/setBasemap before forest layers exist: only basemap visibility changes", () => {
  const m = fakeMap();
  setView(m, P, "borowik", 0);
  setBasemap(m, "topo");
  assert.ok(m.calls.every((c) => c[0] === "layout"));
  assert.equal(m.calls.length, BASEMAP_KEYS.length);
});

test("hExpr: brak atrybutu h_* = 0", () => {
  const s = JSON.stringify(fillColorExpression(null, "borowik", 0));
  assert.ok(s.includes('["to-number",["get","h_borowik"],0]'));
});

test("fillColorExpression dla listy kluczy = max po gatunkach z listy", () => {
  const s = JSON.stringify(fillColorExpression(P, ["kurka", "kozlarz"], 0));
  assert.ok(s.includes('"h_kurka"') && s.includes('"h_kozlarz"'));
  assert.ok(!s.includes('"h_borowik"'));
  assert.ok(s.includes('"max"'));
});

test("fillColorExpression: jednoelementowa lista jak pojedynczy klucz", () => {
  assert.deepEqual(fillColorExpression(P, ["borowik"], 0), fillColorExpression(P, "borowik", 0));
  assert.deepEqual(fillColorExpression(null, ["rydz"], 2), fillColorExpression(null, "rydz", 2));
});

test("parkingIcon ma wymiary i nieprzezroczyste piksele", () => {
  const icon = parkingIcon();
  assert.equal(icon.width, 24);
  assert.equal(icon.height, 24);
  assert.equal(icon.data.length, 24 * 24 * 4);
  const alphas = new Set([...icon.data].filter((_, i) => i % 4 === 3));
  assert.ok(alphas.has(0) && alphas.has(255), "ma przezroczyste i nieprzezroczyste piksele");
});

test("addForestLayers dodaje warstwę parkingi od zoomu 11", () => {
  const m = fakeMap();
  addForestLayers(m, "https://d.example.pl/v/b1/lasy.pmtiles", { pogoda: P, species: "borowik", dayIdx: 0, basemap: "osm" });
  const layers = m.calls.filter((c) => c[0] === "layer").map((c) => c[1]);
  assert.deepEqual(layers, ["lasy-fill", "lasy-rez-hatch", "lasy-line", "rezerwaty-fill", "rezerwaty-line", "parkingi"]);
  const p = m.calls.find((c) => c[0] === "layer" && c[1] === "parkingi")?.[2];
  assert.ok(p);
  assert.equal(p.type, "symbol");
  assert.equal(p["source-layer"], "parkingi");
  assert.equal(p.minzoom, 11);
  assert.equal(p.layout["icon-image"], "parking");
  assert.equal(p.layout["icon-allow-overlap"], true);
  assert.ok(m.calls.some((c) => c[0] === "image" && c[1] === "parking"));
});

import { createMap } from "../js/map.js";

test("klik: parking ma pierwszeństwo przed wydzieleniem", () => {
  globalThis.pmtiles = { Protocol: class { tile() {} } };
  const calls = [];
  const features = {};
  let mapObj;
  globalThis.maplibregl = {
    addProtocol: () => {},
    Map: class {
      constructor(opts) {
        this.container = opts.container;
        mapObj = this;
      }
      getLayer(id) { return features[id] ? { id } : undefined; }
      queryRenderedFeatures(pt, opts) {
        calls.push(["query", pt, opts.layers]);
        const id = opts.layers[0];
        return features[id] ? [features[id]] : [];
      }
      getCanvas() { return { style: {} }; }
      on(ev, fn) { if (ev === "click") this._click = fn; }
      once() {}
      addControl() {}
    },
    NavigationControl: class {},
  };
  createMap("map-container", {
    center: [0, 0],
    zoom: 10,
    onFeatureClick: () => calls.push(["feature"]),
    onReserveClick: () => calls.push(["reserve"]),
    onParkingClick: () => calls.push(["parking"]),
  });
  features["parkingi"] = { properties: { osm: "n1" } };
  features["lasy-fill"] = { properties: { id: "x" } };
  mapObj._click({ point: [5, 5], lngLat: { lat: 0, lng: 0 } });
  assert.deepEqual(calls, [["query", [5, 5], ["parkingi"]], ["parking"]]);
  delete globalThis.pmtiles;
  delete globalThis.maplibregl;
});

// --- wilgotność miejsca (spec L): mały ewaluator wyrażeń MapLibre (tylko używane operatory) ---
import { adjustW, score, scoreClass } from "../js/data.js";

function evalExpr(e, props, env = {}) {
  if (!Array.isArray(e)) return e;
  const [op, ...a] = e;
  const ev = (x, en = env) => evalExpr(x, props, en);
  switch (op) {
    case "literal": return a[0];
    case "get": return props[a[0]];
    case "has": return a[0] in props;
    case "var": return env[a[0]];
    case "let": {
      const en = { ...env };
      for (let i = 0; i < a.length - 1; i += 2) en[a[i]] = ev(a[i + 1], en);
      return ev(a[a.length - 1], en);
    }
    // jak w MapLibre: null -> 0 (nie kolejny argument)
    case "to-number": { const v = ev(a[0]); return v == null ? 0 : Number(v); }
    case "coalesce": { for (const x of a) { const v = ev(x); if (v != null) return v; } return null; }
    case "at": return ev(a[1])[a[0]];
    case "match": {
      const v = ev(a[0]);
      for (let i = 1; i < a.length - 1; i += 2) if (a[i] === v) return ev(a[i + 1]);
      return ev(a[a.length - 1]);
    }
    case "case": {
      for (let i = 0; i < a.length - 1; i += 2) if (ev(a[i])) return ev(a[i + 1]);
      return ev(a[a.length - 1]);
    }
    case "step": {
      const x = ev(a[0]);
      let out = ev(a[1]);
      for (let i = 2; i < a.length; i += 2) if (x >= a[i]) out = ev(a[i + 1]);
      return out;
    }
    case "<": return ev(a[0]) < ev(a[1]);
    case ">": return ev(a[0]) > ev(a[1]);
    case "min": return Math.min(...a.map((x) => ev(x)));
    case "max": return Math.max(...a.map((x) => ev(x)));
    case "*": return a.reduce((p, x) => p * ev(x), 1);
    case "-": return ev(a[0]) - ev(a[1]);
    case "/": return ev(a[0]) / ev(a[1]);
    case "^": return ev(a[0]) ** ev(a[1]);
    case "round": { const v = ev(a[0]); return Math.sign(v) * Math.round(Math.abs(v)); }
    default: throw new Error("nieobsługiwany operator " + op);
  }
}

const WET_P = { days: ["2026-10-04"], cells: { c1: { borowik: { w: [0.797], rain: [0.797] }, podgrzybek: { w: [0.6], rain: [0.9] } } } };

test("mapa: kolor wydzielenia zgodny z adjustW dla różnych wet", () => {
  const expr = fillColorExpression(WET_P, "borowik", 0);
  for (const wet of [undefined, 0, 8, 50, 92, 100]) {
    for (const h of [40, 63, 85]) {
      const props = { cell: "c1", h_borowik: h, ...(wet != null && { wet }) };
      const s = score(h, adjustW(0.797, 0.797, wet ?? null));
      assert.equal(evalExpr(expr, props), classFill(scoreClass(s)), `wet=${wet} h=${h}`);
    }
  }
});

test("mapa: tryb wszystkich gatunków — max po skorygowanych wynikach, brak komórki = noData", () => {
  const expr = fillColorExpression(WET_P, ["borowik", "podgrzybek"], 0);
  const props = { cell: "c1", h_borowik: 85, h_podgrzybek: 80, wet: 8 };
  const best = Math.max(score(85, adjustW(0.797, 0.797, 8)), score(80, adjustW(0.6, 0.9, 8)));
  assert.equal(evalExpr(expr, props), classFill(scoreClass(best)));
  assert.equal(evalExpr(expr, { cell: "zzz", h_borowik: 85, wet: 8 }), NO_DATA_FILL);
});

test("mapa: pogoda bez rain (stary format) — bez korekty", () => {
  const p = { days: ["d"], cells: { c1: { borowik: { w: [0.5] } } } };
  const expr = fillColorExpression(p, "borowik", 0);
  assert.equal(evalExpr(expr, { cell: "c1", h_borowik: 90, wet: 0 }), classFill(scoreClass(45)));
});

import { setWetGammas } from "../js/data.js";

test("mapa: wet_gamma gatunku w wyrażeniu", () => {
  setWetGammas([{ key: "borowik", wet_gamma: 1.5 }]);
  try {
    const expr = fillColorExpression(WET_P, "borowik", 0);
    for (const wet of [0, 30, 100]) {
      const s = score(85, adjustW(0.797, 0.797, wet, 1.5));
      assert.equal(evalExpr(expr, { cell: "c1", h_borowik: 85, wet }), classFill(scoreClass(s)));
    }
  } finally {
    setWetGammas([]);
  }
});

test("mapa: korekta wilgotności miejsca z moist (spec M), nie z rain", () => {
  const p = { days: ["d"], cells: { c1: { borowik: { w: [0.4], rain: [1], moist: [0.5] } } } };
  const expr = fillColorExpression(p, "borowik", 0);
  for (const wet of [0, 50, 100]) {
    const s = score(85, adjustW(0.4, 0.5, wet));
    assert.equal(evalExpr(expr, { cell: "c1", h_borowik: 85, wet }), classFill(scoreClass(s)), `wet=${wet}`);
  }
});

import { DETAIL_ZOOM } from "../js/map.js";

test("klik w las poniżej DETAIL_ZOOM przybliża mapę zamiast otwierać popup", () => {
  globalThis.pmtiles = { Protocol: class { tile() {} } };
  const calls = [];
  let mapObj;
  globalThis.maplibregl = {
    addProtocol: () => {},
    Map: class {
      constructor() { mapObj = this; this.zoom = 9.5; }
      getLayer() { return { id: "lasy-fill" }; }
      getZoom() { return this.zoom; }
      easeTo(o) { calls.push(["ease", o.zoom]); }
      queryRenderedFeatures(pt, opts) { return opts.layers[0] === "lasy-fill" ? [{ properties: { cell: "c1" } }] : []; }
      getCanvas() { return { style: {} }; }
      on(ev, fn) { if (ev === "click") this._click = fn; }
      once() {}
      addControl() {}
    },
    NavigationControl: class {},
  };
  createMap("m", { center: [0, 0], zoom: 9, onFeatureClick: () => calls.push(["feature"]) });
  mapObj._click({ point: [1, 1], lngLat: { lat: 50, lng: 17 } });
  mapObj.zoom = DETAIL_ZOOM;
  mapObj._click({ point: [1, 1], lngLat: { lat: 50, lng: 17 } });
  assert.deepEqual(calls, [["ease", DETAIL_ZOOM + 1], ["feature"]]);
  delete globalThis.pmtiles;
  delete globalThis.maplibregl;
});
