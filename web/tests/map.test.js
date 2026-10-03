import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { fillColorExpression, COLORS } from "../js/map.js";

const P = JSON.parse(fs.readFileSync(new URL("../../tests/fixtures/pogoda.json", import.meta.url), "utf8"));

test("expression contains match on cell with fallback -1", () => {
  const e = JSON.stringify(fillColorExpression(P, "borowik", 0));
  assert.ok(e.includes('"match"') && e.includes('"cell"') && e.includes("-1"));
});

test("expression without pogoda uses h only", () =>
  assert.ok(!JSON.stringify(fillColorExpression(null, "borowik", 0)).includes('"match"')));

test("missing cell falls back to gray 'brak danych'", () => {
  const e = JSON.stringify(fillColorExpression(P, "borowik", 0));
  assert.ok(e.includes(COLORS.noData));
});

test("expression reads h_<species> and uses 5 class colors", () => {
  const e = JSON.stringify(fillColorExpression(P, "rydz", 0));
  assert.ok(e.includes("h_rydz"));
  for (const c of COLORS.classes) assert.ok(e.includes(c));
});
