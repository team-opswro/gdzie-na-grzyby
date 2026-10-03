import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { SPECIES, weatherFor, score, scoreClass, isStale, availableDays, loadData } from "../js/data.js";

const P = JSON.parse(fs.readFileSync(new URL("../../tests/fixtures/pogoda.json", import.meta.url), "utf8"));

test("SPECIES order", () => {
  assert.deepEqual(SPECIES.map((s) => s.key), ["borowik", "podgrzybek", "kurka", "kozlarz", "maslak", "rydz"]);
});
test("weatherFor returns fixture values", () => {
  const w = weatherFor(P, "506_178", "borowik", 2);
  const src = P.cells["506_178"].borowik;
  assert.deepEqual(w, { w: src.w[2], rain: src.rain[2], temp: src.temp[2], season: src.season[2] });
  assert.equal(weatherFor(P, "507_178", "kurka", 0).w, 0);
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

function mockFetch(map) {
  return async (url) => {
    const r = map[url];
    if (r === undefined || r === "throw") throw new Error("net");
    return { ok: r !== 500, status: r === 500 ? 500 : 200, json: async () => r };
  };
}
test("loadData ok", async () => {
  const c = { species: [], rows: [] };
  globalThis.fetch = mockFetch({ "data/centroidy.json": c, "data/live/pogoda.json": P });
  const d = await loadData();
  assert.deepEqual(d, { pogoda: P, centroids: c });
});
test("loadData pogoda failure → null; non-OK → null", async () => {
  const c = { species: [], rows: [] };
  globalThis.fetch = mockFetch({ "data/centroidy.json": c, "data/live/pogoda.json": "throw" });
  assert.equal((await loadData()).pogoda, null);
  globalThis.fetch = mockFetch({ "data/centroidy.json": c, "data/live/pogoda.json": 500 });
  assert.equal((await loadData()).pogoda, null);
});
test("loadData centroids failure throws", async () => {
  globalThis.fetch = mockFetch({ "data/centroidy.json": "throw", "data/live/pogoda.json": P });
  await assert.rejects(loadData());
});
