import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { haversineKm, topN } from "../js/ranking.js";
import { score } from "../js/data.js";

const P = JSON.parse(fs.readFileSync(new URL("../../tests/fixtures/pogoda.json", import.meta.url), "utf8"));
const wWet = P.cells["506_178"].borowik.w[0];

test("haversine Opole–Wrocław ≈ 79 km", () =>
  assert.ok(Math.abs(haversineKm({ lat: 50.675, lon: 17.921 }, { lat: 51.11, lon: 17.032 }) - 79) < 2));

const SP = ["borowik", "podgrzybek", "kurka", "kozlarz", "maslak", "rydz"];
const row = (id, lat, lon, cell, h) => [id, lat, lon, cell, h, 0, 0, 0, 0, 0];
const origin = { lat: 50.675, lon: 17.921 };
const C = {
  species: SP,
  rows: [
    row(5, 50.68, 17.92, "506_178", 50),
    row(2, 50.68, 17.93, "506_178", 50), // tie with 5 → id asc
    row(9, 50.67, 17.91, "506_178", 90),
    row(7, 50.68, 17.92, "507_178", 90), // dry → score 0, skipped
    row(8, 50.68, 17.92, "999_999", 90), // missing cell
    row(1, 51.11, 17.03, "506_178", 100), // too far
    row(3, 50.67, 17.92, "506_178", 0), // h 0
  ],
};

test("topN radius, order, ties, skips missing/zero", () => {
  const r = topN(C, P, "borowik", 0, origin);
  assert.deepEqual(r.map((x) => x.id), [9, 2, 5]);
  assert.equal(r[0].score, score(90, wWet));
  assert.equal(r[1].score, score(50, wWet));
  assert.deepEqual(Object.keys(r[0]).sort(), ["distanceKm", "id", "lat", "lon", "score"]);
  assert.equal(r[0].distanceKm, Math.round(r[0].distanceKm * 10) / 10);
});
test("topN limits n, larger radius includes far", () => {
  assert.equal(topN(C, P, "borowik", 0, origin, 20, 2).length, 2);
  assert.ok(topN(C, P, "borowik", 0, origin, 100).some((x) => x.id === 1));
});
test("topN uses species column; null pogoda → []", () => {
  assert.deepEqual(topN(C, P, "kurka", 0, origin), []);
  assert.deepEqual(topN(C, null, "borowik", 0, origin), []);
});
