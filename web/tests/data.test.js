import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { SPECIES, weatherFor, score, scoreClass, isStale, availableDays, loadData, bannerText } from "../js/data.js";

const P = JSON.parse(fs.readFileSync(new URL("../../tests/fixtures/pogoda.json", import.meta.url), "utf8"));

test("SPECIES order", () => {
  assert.deepEqual(SPECIES.map((s) => s.key), ["borowik", "podgrzybek", "kurka", "kozlarz", "maslak", "rydz"]);
});
test("weatherFor returns fixture values", () => {
  const w = weatherFor(P, "506_178", "borowik", 2);
  const src = P.cells["506_178"].borowik;
  assert.deepEqual(w, {
    w: src.w[2], rain: src.rain[2], temp: src.temp[2], season: src.season[2],
    lim: src.lim[2] ?? null,
    wx: { rain_mm: P.wx["506_178"].rain_mm[2], soil_t: P.wx["506_178"].soil_t[2], soil_m: P.wx["506_178"].soil_m[2] },
  });
  assert.equal(weatherFor(P, "507_178", "kurka", 0).w, 0);
});
test("weatherFor on v1 fixture: lim and wx null", () => {
  const V1 = JSON.parse(fs.readFileSync(new URL("../../tests/fixtures/pogoda_v1.json", import.meta.url), "utf8"));
  const cell = Object.keys(V1.cells)[0];
  const src = V1.cells[cell].borowik;
  assert.deepEqual(weatherFor(V1, cell, "borowik", 0),
    { w: src.w[0], rain: src.rain[0], temp: src.temp[0], season: src.season[0], lim: null, wx: null });
});
test("weatherFor cell absent from wx → wx null", () => {
  const Q = { ...P, wx: {} };
  const r = weatherFor(Q, "506_178", "borowik", 2);
  assert.equal(r.wx, null);
  assert.notEqual(r.w, null);
});
test("weatherFor missing cell → null", () => assert.equal(weatherFor(P, "999_999", "borowik", 0), null));
test("weatherFor null pogoda → null", () => assert.equal(weatherFor(null, "506_178", "borowik", 0), null));
test("score", () => { assert.equal(score(80, 0.5), 40); assert.equal(score(80, null), null); });
test("scoreClass bounds", () => {
  assert.deepEqual([9, 10, 25, 45, 65, 66].map(scoreClass), [0, 1, 2, 3, 3, 4]);
  assert.equal(scoreClass(null), null);
});
test("isStale 36h", () => {
  assert.equal(isStale("2026-10-01T05:00:00+02:00", new Date("2026-10-02T17:00:00+02:00")), false);
  assert.equal(isStale("2026-10-01T05:00:00+02:00", new Date("2026-10-02T17:01:00+02:00")), true);
});
test("availableDays drops past", () =>
  assert.deepEqual(availableDays(["2026-10-02", "2026-10-03", "2026-10-04"], "2026-10-03").map((d) => d.idx), [1, 2]));
test("availableDays on fixture days keeps all when today is first day", () =>
  assert.equal(availableDays(P.days, P.days[0]).length, P.days.length));

const NZ = { nadl: { "02-04": "Brzeg" }, lesn: {} };
function mockFetch(map) {
  return async (url) => {
    const r = map[url];
    if (r === undefined || r === "throw") throw new Error("net");
    return { ok: r !== 500, status: r === 500 ? 500 : 200, json: async () => r };
  };
}
test("loadData ok", async () => {
  const c = { species: [], rows: [] };
  globalThis.fetch = mockFetch({ "data/centroidy.json": c, "data/live/pogoda.json": P, "data/nazwy.json": NZ });
  const d = await loadData();
  assert.deepEqual(d, { pogoda: P, centroids: c, nazwy: NZ });
});
test("loadData pogoda failure → null; non-OK → null", async () => {
  const c = { species: [], rows: [] };
  globalThis.fetch = mockFetch({ "data/centroidy.json": c, "data/live/pogoda.json": "throw" });
  assert.equal((await loadData()).pogoda, null);
  globalThis.fetch = mockFetch({ "data/centroidy.json": c, "data/live/pogoda.json": 500 });
  assert.equal((await loadData()).pogoda, null);
});
test("loadData centroids failure → centroids null, pogoda kept", async () => {
  globalThis.fetch = mockFetch({ "data/centroidy.json": "throw", "data/live/pogoda.json": P });
  assert.deepEqual(await loadData(), { pogoda: P, centroids: null, nazwy: null });
  globalThis.fetch = mockFetch({ "data/centroidy.json": 500, "data/live/pogoda.json": P });
  assert.deepEqual(await loadData(), { pogoda: P, centroids: null, nazwy: null });
});
test("loadData both fail → both null", async () => {
  globalThis.fetch = mockFetch({ "data/centroidy.json": "throw", "data/live/pogoda.json": "throw" });
  assert.deepEqual(await loadData(), { pogoda: null, centroids: null, nazwy: null });
});
test("bannerText states", () => {
  const now = new Date("2026-10-03T12:00:00+02:00");
  const fresh = { generated_at: "2026-10-03T05:00:00+02:00" };
  const old = { generated_at: "2026-10-01T05:00:00+02:00" };
  assert.equal(bannerText(fresh, 3, now), null);
  assert.equal(bannerText(null, 0, now), "Brak danych pogodowych — mapa pokazuje tylko ocenę siedliska");
  assert.equal(bannerText(old, 2, now), "Prognoza nieaktualna (z dnia 2026-10-01)");
  assert.equal(bannerText(old, 0, now), "Prognoza nieaktualna (z dnia 2026-10-01), mapa pokazuje tylko ocenę siedliska");
  assert.match(bannerText(fresh, 0, now), /tylko ocenę siedliska/);
});
test("isStale unparseable date → true", () => assert.equal(isStale("garbage", new Date()), true));

test("weatherFor: partially missing wx values -> wx null", () => {
  const p = { days: ["d"], cells: { c: { borowik: { w: [0.5], rain: [1], temp: [1], season: [1], lim: [null] } } },
    wx: { c: { rain_mm: [3], soil_t: [null], soil_m: [0.2] } } };
  assert.equal(weatherFor(p, "c", "borowik", 0).wx, null);
});
test("loadData nazwy failure → nazwy null, rest unchanged", async () => {
  const c = { species: [], rows: [] };
  globalThis.fetch = mockFetch({ "data/centroidy.json": c, "data/live/pogoda.json": P, "data/nazwy.json": "throw" });
  assert.deepEqual(await loadData(), { pogoda: P, centroids: c, nazwy: null });
  globalThis.fetch = mockFetch({ "data/centroidy.json": c, "data/live/pogoda.json": P, "data/nazwy.json": 500 });
  assert.deepEqual(await loadData(), { pogoda: P, centroids: c, nazwy: null });
});
