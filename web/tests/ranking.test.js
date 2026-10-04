import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { haversineKm, topN, bearing, renderLoading } from "../js/ranking.js";
import { score } from "../js/data.js";
import { installDom } from "./dom-stub.js";

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
  assert.deepEqual(Object.keys(r[0].best).sort(), ["cell", "h", "id", "lat", "lon", "score", "wet"]);
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

test("topN all: row score = best species, group has species and its h", () => {
  const rowA = (id, cell, hs) => [id, 50.68, 17.92, cell, ...hs];
  const C2 = { species: SP, rows: [rowA("02-40-1-12-363-i-00", "506_178", [10, 100, 10, 10, 10, 10])] };
  const r = topN(C2, P, "all", 0, origin, 20, 10);
  assert.equal(r.length, 1);
  assert.equal(r[0].species, "podgrzybek");
  assert.equal(r[0].best.h, 100);
  assert.equal(r[0].best.score, score(100, P.cells["506_178"].podgrzybek.w[0]));
  assert.equal(topN(C2, null, "all", 0, origin).length, 0);
});
test("topN all with pogoda_v1 does not throw", () => {
  const V1 = JSON.parse(fs.readFileSync(new URL("../../tests/fixtures/pogoda_v1.json", import.meta.url), "utf8"));
  const C2 = { species: SP, rows: [["02-40-1-12-363-i-00", 50.68, 17.92, "506_178", 50, 50, 50, 50, 50, 50]] };
  assert.doesNotThrow(() => topN(C2, V1, "all", 0, origin));
});

test("topN grupy: najlepszy gatunek z listy kluczy", () => {
  const C2 = { species: SP, rows: [["a", 50.68, 17.92, "506_178", 10, 100, 90, 10, 10, 10]] };
  const r = topN(C2, P, ["kurka", "kozlarz"], 0, origin);
  assert.equal(r.length, 1);
  assert.equal(r[0].species, "kurka");
  assert.equal(r[0].best.h, 90);
});

test("topN pomija klucze spoza centroids.species", () => {
  const C2 = { species: SP, rows: [["a", 50.68, 17.92, "506_178", 10, 100, 90, 10, 10, 10]] };
  const r = topN(C2, P, ["nieznany", "kurka"], 0, origin);
  assert.equal(r.length, 1);
  assert.equal(r[0].best.h, 90); // kolumna kurki, nie przesunięta przez nieznany klucz
  assert.deepEqual(topN(C2, P, ["nieznany"], 0, origin), []);
});

test("renderLoading ustawia aria-busy i komunikat", () => {
  installDom();
  const list = {
    setAttribute: function (k, v) { this.attrs[k] = v; },
    replaceChildren: function (...c) { this.children = c; },
    attrs: {},
    children: [],
  };
  renderLoading(list);
  assert.equal(list.attrs["aria-busy"], "true");
  assert.equal(list.children.length, 1);
  assert.equal(list.children[0].tag, "li");
  assert.equal(list.children[0].className, "empty");
  assert.equal(list.children[0].textContent, "Ładowanie…");
});

test("index.html ma tytuł Gdzie na grzyby?", () => {
  const html = fs.readFileSync(new URL("../index.html", import.meta.url), "utf8");
  assert.match(html, /<title>\s*Gdzie na grzyby\?\s*<\/title>/);
});

// --- wilgotność miejsca (spec L): kolumna wet za h_* (index.json "extra") ---
import { weatherFor } from "../js/data.js";

test("topN uwzględnia wet z kolumny extra; bez extra — po staremu", () => {
  const rain = P.cells["506_178"].borowik.rain[0];
  assert.ok(rain > 0 && rain < 1, "fixture: dzień z niepełnym opadem");
  const rows = [[...row("a", 50.68, 17.92, "506_178", 60), 100], [...row("b", 50.68, 17.93, "506_178", 66), 0]];
  const withWet = topN({ species: SP, extra: ["wet"], rows }, P, "borowik", 0, origin);
  assert.deepEqual(withWet.map((g) => g.best.id), ["a", "b"]);
  assert.equal(withWet[0].best.score, score(60, weatherFor(P, "506_178", "borowik", 0, 100).w));
  const legacy = topN({ species: SP, rows }, P, "borowik", 0, origin);
  assert.deepEqual(legacy.map((g) => g.best.id), ["b", "a"]);
});

test("topN: najlepszy kandydat niesie wet (trend w rankingu liczony jak wynik)", () => {
  const rows = [[...row("a", 50.68, 17.92, "506_178", 60), 77]];
  assert.equal(topN({ species: SP, extra: ["wet"], rows }, P, "borowik", 0, origin)[0].best.wet, 77);
  assert.equal(topN({ species: SP, rows }, P, "borowik", 0, origin)[0].best.wet, null);
});
