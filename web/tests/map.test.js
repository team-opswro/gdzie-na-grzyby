import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { fillColorExpression, fillOpacityExpression, COLORS, FILL_OPACITY, hatchPattern, BASEMAPS, lineColor } from "../js/map.js";
import { BASEMAP_KEYS } from "../js/hash.js";

const P = JSON.parse(fs.readFileSync(new URL("../../tests/fixtures/pogoda.json", import.meta.url), "utf8"));

test("expression contains match on cell with fallback -1", () => {
  const e = JSON.stringify(fillColorExpression(P, "borowik", 0));
  assert.ok(e.includes('"match"') && e.includes('"cell"') && e.includes("-1"));
});

test("expression without pogoda uses h only", () =>
  assert.ok(!JSON.stringify(fillColorExpression(null, "borowik", 0)).includes('"match"')));

test("noData color is distinct from every class color", () =>
  assert.ok(!COLORS.classes.includes(COLORS.noData)));

test("missing-cell branch yields the noData color and opacity", () => {
  const c = fillColorExpression(P, "borowik", 0)[3];
  assert.deepEqual(c[3], ["case", ["<", ["var", "wv"], 0], COLORS.noData, c[3][3]]);
  const o = fillOpacityExpression(P, "borowik", 0)[3];
  assert.equal(o[3][2], FILL_OPACITY.noData);
  assert.notEqual(FILL_OPACITY.noData, FILL_OPACITY.weak);
});

test("expression reads h_<species> and uses 5 class colors", () => {
  const e = JSON.stringify(fillColorExpression(P, "rydz", 0));
  assert.ok(e.includes("h_rydz"));
  for (const c of COLORS.classes) assert.ok(e.includes(c));
});

test("reserve branch comes first", () => {
  for (const p of [P, null]) {
    const c = fillColorExpression(p, "borowik", 0);
    assert.deepEqual(c.slice(0, 3), ["case", ["has", "rez"], COLORS.reserve]);
    assert.equal(fillOpacityExpression(p, "borowik", 0)[2], FILL_OPACITY.reserve);
  }
  assert.ok(!COLORS.classes.includes(COLORS.reserve) && COLORS.reserve !== COLORS.noData);
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
  assert.equal(fillOpacityExpression(P, "all", 0)[1][0], "has");
});
test("all without pogoda: max of h_*, no match", () => {
  for (const e of [fillColorExpression(null, "all", 0), fillOpacityExpression(null, "all", 0)]) {
    const s = JSON.stringify(e);
    assert.ok(s.includes('"max"') && !s.includes('"match"'));
    for (const k of SPECIES) assert.ok(s.includes("h_" + k.key));
  }
});
test("all with old pogoda_v1 does not throw", () => {
  assert.doesNotThrow(() => { fillColorExpression(V1, "all", 0); fillOpacityExpression(V1, "all", 3); });
});

import { addForestLayers, setView, setBasemap } from "../js/map.js";

function fakeMap(layers = []) {
  const calls = [];
  const have = new Set(layers);
  return {
    calls,
    getLayer: (id) => (have.has(id) ? { id } : undefined),
    addSource: (id, src) => calls.push(["source", id, src]),
    addImage: (id) => calls.push(["image", id]),
    addLayer: (l) => { have.add(l.id); calls.push(["layer", l.id]); },
    setPaintProperty: (id, k) => calls.push(["paint", id, k]),
    setLayoutProperty: (id, k, v) => calls.push(["layout", id, v]),
  };
}

test("addForestLayers: pmtiles source from absolute URL, layers in order", () => {
  const m = fakeMap();
  addForestLayers(m, "https://d.example.pl/v/b1/lasy.pmtiles", { pogoda: P, species: "borowik", dayIdx: 0, basemap: "orto" });
  const src = m.calls.find((c) => c[0] === "source");
  assert.equal(src[1], "lasy");
  assert.equal(src[2].url, "pmtiles://https://d.example.pl/v/b1/lasy.pmtiles");
  assert.deepEqual(m.calls.filter((c) => c[0] === "layer").map((c) => c[1]),
    ["lasy-fill", "lasy-rez-hatch", "lasy-line", "rezerwaty-fill", "rezerwaty-line"]);
  assert.ok(m.calls.some((c) => c[0] === "image" && c[1] === "hatch"));
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
