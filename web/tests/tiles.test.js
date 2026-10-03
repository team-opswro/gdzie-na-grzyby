import test from "node:test";
import assert from "node:assert/strict";
import { tileKey, tilesForRadius, tilesAround, createCentroidStore } from "../js/tiles.js";

const keysIn = (lats, lons) => lats.flatMap((a) => lons.map((o) => `${a.toFixed(1)}_${o.toFixed(1)}`));
const IDX = { tile: 0.5, species: ["borowik", "kurka"], tiles: keysIn([49.5, 50, 50.5, 51], [16.5, 17, 17.5, 18]) };

test("tileKey: floor to 0.5°, one decimal", () => {
  assert.equal(tileKey(50.95938, 17.4582), "50.5_17.0");
  assert.equal(tileKey(50.5, 17.0), "50.5_17.0");
  assert.equal(tileKey(50.49999, 16.99999), "50.0_16.5");
  assert.equal(tileKey(-0.2, -0.2), "-0.5_-0.5");
});

test("tilesForRadius: radius inside one tile → single tile", () => {
  assert.deepEqual(tilesForRadius({ lat: 50.75, lon: 17.25 }, 5, IDX), ["50.5_17.0"]);
});

test("tilesForRadius: origin on tile boundary covers both sides", () => {
  const t = tilesForRadius({ lat: 50.5, lon: 17.0 }, 5, IDX).sort();
  assert.deepEqual(t, ["50.0_16.5", "50.0_17.0", "50.5_16.5", "50.5_17.0"]);
});

test("tilesForRadius: lon span grows with latitude (bbox lat ±r/111, lon ±r/(111 cos lat))", () => {
  // r = 40 km at 50.75°: dLat ≈ 0.36°, dLon ≈ 0.57° → lat 50.39–51.11, lon 16.68–17.82
  const t = tilesForRadius({ lat: 50.75, lon: 17.25 }, 40, IDX).sort();
  assert.deepEqual(t, keysIn([50, 50.5, 51], [16.5, 17, 17.5]).sort());
  // high latitude: cos small → many lon tiles, still only those in index
  const polar = { tile: 0.5, species: [], tiles: ["80.0_10.0", "80.0_20.0", "80.0_40.0"] };
  assert.deepEqual(tilesForRadius({ lat: 80.2, lon: 15 }, 100, polar).sort(), ["80.0_10.0", "80.0_20.0"]);
});

test("tilesForRadius: only tiles present in index; area without tiles → []", () => {
  assert.deepEqual(tilesForRadius({ lat: 54.0, lon: 22.0 }, 20, IDX), []);
  assert.deepEqual(tilesForRadius({ lat: 50.75, lon: 17.25 }, 5, null), []);
});

test("tilesAround: 3×3 neighbourhood filtered by index", () => {
  assert.deepEqual(tilesAround(50.75, 17.25, IDX).sort(), keysIn([50, 50.5, 51], [16.5, 17, 17.5]).sort());
  assert.deepEqual(tilesAround(51.2, 18.2, IDX).sort(), keysIn([50.5, 51], [17.5, 18]).sort());
});

function tileFetch(tiles, { fail = [] } = {}) {
  const calls = [];
  const f = async (url) => {
    calls.push(url);
    const key = url.replace(/^.*\//, "").replace(/\.json$/, "");
    if (fail.includes(key)) return { ok: false, status: 404, json: async () => null };
    return { ok: true, status: 200, json: async () => ({ rows: tiles[key] ?? [] }) };
  };
  f.calls = calls;
  return f;
}

const ROWS = {
  "50.5_17.0": [["a", 50.6, 17.1, "506_171", 10, 20]],
  "50.0_17.0": [["b", 50.45, 17.1, "504_171", 30, 40]],
};

test("rowsNear: merges rows of covered tiles, builds URLs from base", async () => {
  const f = tileFetch(ROWS);
  const store = createCentroidStore(f, "https://d.example.pl/v/x/centroidy/", IDX);
  const rows = await store.rowsNear({ lat: 50.5, lon: 17.1 }, 8);
  assert.deepEqual(rows.map((r) => r[0]).sort(), ["a", "b"]);
  assert.ok(f.calls.every((u) => u.startsWith("https://d.example.pl/v/x/centroidy/") && u.endsWith(".json")));
  assert.ok(f.calls.includes("https://d.example.pl/v/x/centroidy/50.5_17.0.json"));
});

test("rowsNear: cache — each tile fetched once, also for concurrent calls", async () => {
  const f = tileFetch(ROWS);
  const store = createCentroidStore(f, "c/", IDX);
  const o = { lat: 50.5, lon: 17.1 };
  await Promise.all([store.rowsNear(o, 8), store.rowsNear(o, 8)]);
  await store.rowsNear(o, 8);
  assert.equal(f.calls.length, new Set(f.calls).size);
  assert.equal(f.calls.length, tilesForRadius(o, 8, IDX).length);
});

test("rowsNear: missing/failed tile → skipped, others returned; retried later", async () => {
  const f = tileFetch(ROWS, { fail: ["50.0_17.0"] });
  const store = createCentroidStore(f, "c/", IDX);
  const rows = await store.rowsNear({ lat: 50.5, lon: 17.1 }, 8);
  assert.deepEqual(rows.map((r) => r[0]), ["a"]);
  await store.rowsNear({ lat: 50.5, lon: 17.1 }, 8);
  assert.equal(f.calls.filter((u) => u === "c/50.0_17.0.json").length, 2);
});

test("rowsNear: all needed tiles failed → rejects (ranking shows the error message)", async () => {
  const thrower = async () => { throw new Error("net"); };
  await assert.rejects(createCentroidStore(thrower, "c/", IDX).rowsNear({ lat: 50.5, lon: 17.1 }, 8), /kafelków/);
  const f = tileFetch(ROWS, { fail: ["50.5_17.0"] });
  await assert.rejects(createCentroidStore(f, "c/", IDX).rowsNear({ lat: 50.75, lon: 17.25 }, 5));
});

test("tile fetch: hung server → aborted after timeoutMs, then rejects; retried on next call", async () => {
  const signals = [];
  let hang = true;
  const f = (url, init) => {
    signals.push(init?.signal);
    if (!hang) return Promise.resolve({ ok: true, status: 200, json: async () => ({ rows: ROWS["50.5_17.0"] }) });
    return new Promise(() => {}); // never resolves
  };
  const store = createCentroidStore(f, "c/", IDX, { timeoutMs: 20 });
  const t0 = Date.now();
  await assert.rejects(store.rowsNear({ lat: 50.75, lon: 17.25 }, 5));
  assert.ok(Date.now() - t0 < 1000);
  assert.ok(signals[0]?.aborted, "fetch aborted via AbortSignal");
  hang = false;
  assert.deepEqual((await store.rowsNear({ lat: 50.75, lon: 17.25 }, 5)).map((r) => r[0]), ["a"]);
});

test("tile fetch: default timeout is 30 s, immutable tiles use default HTTP cache", async () => {
  const { TILE_TIMEOUT_MS } = await import("../js/tiles.js");
  assert.equal(TILE_TIMEOUT_MS, 30000);
  const inits = [];
  const f = async (url, init) => { inits.push(init); return { ok: true, status: 200, json: async () => ({ rows: [] }) }; };
  await createCentroidStore(f, "c/", IDX).rowsNear({ lat: 50.75, lon: 17.25 }, 5);
  assert.equal(inits[0].cache, "default");
});

test("findRow: neighbours all failing → rejects (caller treats as not found)", async () => {
  const f = tileFetch(ROWS, { fail: IDX.tiles });
  await assert.rejects(createCentroidStore(f, "c/", IDX).findRow("a", 50.7, 17.3));
});

test("rowsNear: area without tiles → [] without fetching", async () => {
  const f = tileFetch(ROWS);
  assert.deepEqual(await createCentroidStore(f, "c/", IDX).rowsNear({ lat: 54, lon: 22 }, 20), []);
  assert.equal(f.calls.length, 0);
});

test("findRow: id in 3×3 neighbourhood of center", async () => {
  const f = tileFetch(ROWS);
  const store = createCentroidStore(f, "c/", IDX);
  assert.deepEqual(await store.findRow("b", 50.7, 17.3), ROWS["50.0_17.0"][0]);
  assert.equal(await store.findRow("zzz", 50.7, 17.3), null);
  assert.equal(await store.findRow("a", 53, 22), null);
});

test("findRow: center tile first, neighbours only on miss", async () => {
  const f = tileFetch(ROWS);
  const store = createCentroidStore(f, "c/", IDX);
  assert.deepEqual(await store.findRow("a", 50.7, 17.3), ROWS["50.5_17.0"][0]);
  assert.deepEqual(f.calls, ["c/50.5_17.0.json"]);
  assert.deepEqual(await store.findRow("b", 50.7, 17.3), ROWS["50.0_17.0"][0]);
  assert.equal(f.calls.length, 9); // center cached + 8 neighbours
  // center tile absent from index → neighbours only
  const idx2 = { ...IDX, tiles: IDX.tiles.filter((k) => k !== "50.5_17.0") };
  const f2 = tileFetch(ROWS);
  assert.deepEqual(await createCentroidStore(f2, "c/", idx2).findRow("b", 50.7, 17.3), ROWS["50.0_17.0"][0]);
  assert.ok(!f2.calls.includes("c/50.5_17.0.json"));
});
