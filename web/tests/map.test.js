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
