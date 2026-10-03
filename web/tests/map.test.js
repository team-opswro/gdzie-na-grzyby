import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { fillColorExpression, fillOpacityExpression, COLORS, FILL_OPACITY } from "../js/map.js";

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
  const c = fillColorExpression(P, "borowik", 0);
  assert.deepEqual(c[3], ["case", ["<", ["var", "wv"], 0], COLORS.noData, c[3][3]]);
  const o = fillOpacityExpression(P, "borowik", 0);
  assert.equal(o[3][2], FILL_OPACITY.noData);
  assert.notEqual(FILL_OPACITY.noData, FILL_OPACITY.weak);
});

test("expression reads h_<species> and uses 5 class colors", () => {
  const e = JSON.stringify(fillColorExpression(P, "rydz", 0));
  assert.ok(e.includes("h_rydz"));
  for (const c of COLORS.classes) assert.ok(e.includes(c));
});
