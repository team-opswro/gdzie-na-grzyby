import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { haversineKm, topN, bearing } from "../js/ranking.js";
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
    row("02-40-1-12-363-i-00", 50.68, 17.92, "506_178", 50),
    row("02-04-1-07-368-a-00", 50.68, 17.93, "506_178", 50), // tie with 5 → id asc
    row("09", 50.67, 17.91, "506_178", 90),
    row("07", 50.68, 17.92, "507_178", 90), // dry → score 0, skipped
    row("08", 50.68, 17.92, "999_999", 90), // missing cell
    row("01", 51.11, 17.03, "506_178", 100), // too far
    row("03", 50.67, 17.92, "506_178", 0), // h 0
  ],
};

test("topN radius, order, ties, skips missing/zero", () => {
  const r = topN(C, P, "borowik", 0, origin);
  assert.deepEqual(r.map((x) => x.best.id), ["09", "02-04-1-07-368-a-00", "02-40-1-12-363-i-00"]);
  assert.equal(r[0].best.score, score(90, wWet));
  assert.equal(r[1].best.score, score(50, wWet));
  assert.deepEqual(Object.keys(r[0]).sort(), ["bearing", "best", "count", "distanceKm", "key"]);
  assert.deepEqual(Object.keys(r[0].best).sort(), ["cell", "h", "id", "lat", "lon", "score"]);
  assert.equal(r[0].distanceKm, Math.round(r[0].distanceKm * 10) / 10);
  assert.equal(r[0].key, "09");
  assert.equal(r[0].count, 1);
});
test("topN groups compartments: count and best", () => {
  const G = { species: SP, rows: [
    row("02-04-1-07-368-a-00", 50.68, 17.92, "506_178", 40),
    row("02-04-1-07-368-b-00", 50.69, 17.92, "506_178", 80),
    row("02-04-1-07-368-c-00", 50.69, 17.92, "506_178", 0), // zero, not counted
    row("02-04-1-07-369-a-00", 50.68, 17.93, "506_178", 10),
  ] };
  const r = topN(G, P, "borowik", 0, origin);
  assert.equal(r.length, 2);
  assert.equal(r[0].key, "02-04-1-07-368");
  assert.equal(r[0].count, 2);
  assert.equal(r[0].best.id, "02-04-1-07-368-b-00");
  assert.equal(r[0].bearing, "płn.");
  assert.equal(r[1].count, 1);
});
test("topN tie within group → smaller id", () => {
  const G = { species: SP, rows: [
    row("02-04-1-07-368-b-00", 50.68, 17.92, "506_178", 50),
    row("02-04-1-07-368-a-00", 50.69, 17.92, "506_178", 50),
  ] };
  assert.equal(topN(G, P, "borowik", 0, origin)[0].best.id, "02-04-1-07-368-a-00");
});
test("bearing 8 directions", () => {
  const o = { lat: 50, lon: 17 };
  const d = 0.1, dx = 0.1 / Math.cos(rad50());
  function rad50() { return (50 * Math.PI) / 180; }
  const pts = {
    "płn.": [d, 0], "płn.-wsch.": [d, dx], "wsch.": [0, dx], "płd.-wsch.": [-d, dx],
    "płd.": [-d, 0], "płd.-zach.": [-d, -dx], "zach.": [0, -dx], "płn.-zach.": [d, -dx],
  };
  for (const [name, [dy, dxx]] of Object.entries(pts)) assert.equal(bearing(o, { lat: 50 + dy, lon: 17 + dxx }), name);
});
test("topN limits n, larger radius includes far", () => {
  assert.equal(topN(C, P, "borowik", 0, origin, 20, 2).length, 2);
  assert.ok(topN(C, P, "borowik", 0, origin, 100).some((x) => x.best.id === "01"));
});
test("topN uses species column; null pogoda → []", () => {
  assert.deepEqual(topN(C, P, "kurka", 0, origin), []);
  assert.deepEqual(topN(C, null, "borowik", 0, origin), []);
});
