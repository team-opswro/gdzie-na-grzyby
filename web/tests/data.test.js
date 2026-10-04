import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { LOCAL_MANIFEST } from "../js/config.js";
import { SPECIES, weatherFor, score, scoreClass, isStale, availableDays, loadData, bannerText, DATA_TIMEOUT_MS } from "../js/data.js";
import { FETCH_TIMEOUT_MS } from "../js/config.js";

const P = JSON.parse(fs.readFileSync(new URL("../../tests/fixtures/pogoda.json", import.meta.url), "utf8"));

test("SPECIES order", () => {
  assert.deepEqual(SPECIES.map((s) => s.key).slice(0, 6), ["borowik", "podgrzybek", "kurka", "kozlarz", "maslak", "rydz"]);
  assert.equal(SPECIES.length, 18);
});
test("weatherFor returns fixture values", () => {
  const w = weatherFor(P, "506_178", "borowik", 2);
  const src = P.cells["506_178"].borowik;
  assert.deepEqual(w, {
    w: src.w[2], rain: src.rain[2], temp: src.temp[2], season: src.season[2],
    pulse: src.pulse?.[2] ?? null,
    frost: src.frost?.[2] ?? null,
    lim: src.lim[2] ?? null,
    wx: { rain_mm: P.wx["506_178"].rain_mm[2], soil_t: P.wx["506_178"].soil_t[2], soil_m: P.wx["506_178"].soil_m[2] },
  });
  assert.equal(weatherFor(P, "507_178", "kurka", 0).w, 0);
});

test("weatherFor z nowymi polami wx", () => {
  const Q = JSON.parse(JSON.stringify(P));
  Q.cells["506_178"].borowik.pulse = [1.0, 1.0, 1.1];
  Q.cells["506_178"].borowik.frost = [1.0, 1.0, 0.6];
  Q.wx["506_178"].et0_mm = [10.0, 10.0, 12.0];
  Q.wx["506_178"].soil_m_deep = [0.2, 0.2, 0.25];
  Q.wx["506_178"].t2m_min = [5.0, 5.0, 4.0];
  const w = weatherFor(Q, "506_178", "borowik", 2);
  assert.equal(w.pulse, 1.1);
  assert.equal(w.frost, 0.6);
  assert.deepEqual(w.wx, { rain_mm: 32.0, soil_t: 8.8, soil_m: 0.222, et0_mm: 12.0, soil_m_deep: 0.25, t2m_min: 4.0 });
});
test("weatherFor on v1 fixture: lim and wx null", () => {
  const V1 = JSON.parse(fs.readFileSync(new URL("../../tests/fixtures/pogoda_v1.json", import.meta.url), "utf8"));
  const cell = Object.keys(V1.cells)[0];
  const src = V1.cells[cell].borowik;
  assert.deepEqual(weatherFor(V1, cell, "borowik", 0),
    { w: src.w[0], rain: src.rain[0], temp: src.temp[0], season: src.season[0], pulse: null, frost: null, lim: null, wx: null });
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
    if (typeof r === "number") return { ok: false, status: r, json: async () => null };
    return { ok: true, status: 200, json: async () => r };
  };
}
const IDXC = { tile: 0.5, species: ["borowik"], tiles: ["50.5_17.0"] };
const LOCAL = { "data/manifest.json": 404, "data/centroidy/index.json": IDXC, "data/live/pogoda.json": P, "data/nazwy.json": NZ };
test("loadData: data/ without manifest reads files from data/ root, pogoda from live/", async () => {
  globalThis.fetch = mockFetch(LOCAL);
  const d = await loadData({ dataBase: "data/" });
  assert.deepEqual(d.pogoda, P);
  assert.deepEqual(d.centroidIndex, IDXC);
  assert.deepEqual(d.nazwy, NZ);
  assert.equal(d.dataBase, "data/");
  assert.equal(d.manifest.base, "");
});
test("loadData: without arguments reads config.json (missing → data/)", async () => {
  globalThis.fetch = mockFetch({ ...LOCAL, "config.json": 404 });
  const d = await loadData();
  assert.equal(d.dataBase, "data/");
  assert.deepEqual(d.centroidIndex, IDXC);
});
test("loadData: bucket with manifest reads versioned files; pogoda from live/", async () => {
  const B = "https://d.example.pl/";
  const M = { build: "b1", base: "v/b1/", files: { centroidy: "centroidy/index.json", nazwy: "nazwy.json", lasy: "lasy.pmtiles" } };
  globalThis.fetch = mockFetch({
    "config.json": { dataBase: "https://d.example.pl" },
    [B + "manifest.json"]: M,
    [B + "v/b1/centroidy/index.json"]: IDXC,
    [B + "v/b1/nazwy.json"]: NZ,
    [B + "live/pogoda.json"]: P,
  });
  const d = await loadData();
  assert.deepEqual(d, { pogoda: P, centroidIndex: IDXC, nazwy: NZ, manifest: M, dataBase: B });
});
test("loadData pogoda failure → null; non-OK → null", async () => {
  globalThis.fetch = mockFetch({ ...LOCAL, "data/live/pogoda.json": "throw" });
  assert.equal((await loadData({ dataBase: "data/" })).pogoda, null);
  globalThis.fetch = mockFetch({ ...LOCAL, "data/live/pogoda.json": 500 });
  assert.equal((await loadData({ dataBase: "data/" })).pogoda, null);
});
test("loadData centroid index failure → null, pogoda kept", async () => {
  for (const r of ["throw", 500]) {
    globalThis.fetch = mockFetch({ ...LOCAL, "data/centroidy/index.json": r });
    const d = await loadData({ dataBase: "data/" });
    assert.equal(d.centroidIndex, null);
    assert.deepEqual(d.pogoda, P);
  }
});
test("loadData everything fails → nulls", async () => {
  globalThis.fetch = mockFetch({});
  const d = await loadData({ dataBase: "data/" });
  assert.equal(d.pogoda, null); assert.equal(d.centroidIndex, null); assert.equal(d.nazwy, null);
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
  for (const r of ["throw", 500]) {
    globalThis.fetch = mockFetch({ ...LOCAL, "data/nazwy.json": r });
    const d = await loadData({ dataBase: "data/" });
    assert.equal(d.nazwy, null);
    assert.deepEqual(d.pogoda, P);
    assert.deepEqual(d.centroidIndex, IDXC);
  }
});

import { ALL, loadSpecies } from "../js/data.js";

test("ALL key", () => assert.equal(ALL, "all"));
test("loadSpecies reads list from gatunki.json", async () => {
  const doc = { reviewed: false, species: [{ key: "borowik", name: "Borowik szlachetny", latin: "Boletus edulis" }] };
  const orig = globalThis.fetch;
  let url;
  globalThis.fetch = async (u) => { url = u; return { ok: true, json: async () => doc }; };
  try {
    const r = await loadSpecies("https://d.example.pl/v/b1/gatunki.json");
    assert.equal(url, "https://d.example.pl/v/b1/gatunki.json");
    assert.deepEqual(r.list, doc.species);
    assert.deepEqual(r.info, doc);
  } finally { globalThis.fetch = orig; }
});
test("loadSpecies falls back to SPECIES on 404 / exception / bad shape", async () => {
  const orig = globalThis.fetch;
  try {
    for (const f of [async () => ({ ok: false, status: 404 }), async () => { throw new Error("net"); }, async () => ({ ok: true, json: async () => ({ species: [] }) })]) {
      globalThis.fetch = f;
      const r = await loadSpecies();
      assert.deepEqual(r.list, SPECIES);
      assert.equal(r.info, null);
    }
  } finally { globalThis.fetch = orig; }
});

test("loadSpecies: zawieszony fetch -> po limicie czasu SPECIES", async () => {
  const orig = globalThis.fetch;
  globalThis.fetch = () => new Promise(() => {});
  try {
    const r = await loadSpecies("data/gatunki.json", 20);
    assert.deepEqual(r.list, SPECIES);
    assert.equal(r.info, null);
  } finally { globalThis.fetch = orig; }
});

import { bestFor } from "../js/data.js";

test("bestFor: max over species, skips species without data, null when none", () => {
  const h = { borowik: 100, podgrzybek: 100, kurka: 100, kozlarz: 100, maslak: 100, rydz: 100 };
  const b = bestFor(P, "506_178", h, 0);
  const expect = Math.max(...Object.keys(h).map((k) => score(100, P.cells["506_178"][k].w[0])));
  assert.equal(b.score, expect);
  assert.equal(b.species, "podgrzybek");
  assert.deepEqual(b.wx, weatherFor(P, "506_178", b.species, 0));
  // tylko gatunek bez danych w komórce
  const P2 = { days: ["d"], cells: { c: { borowik: { w: [0.5], rain: [0], temp: [0], season: [0] } } } };
  assert.deepEqual(bestFor(P2, "c", { borowik: 40, rydz: 90 }, 0).species, "borowik");
  assert.equal(bestFor(P2, "c", { rydz: 90 }, 0), null);
  assert.equal(bestFor(P2, "zzz", { borowik: 40 }, 0), null);
  assert.equal(bestFor(null, "c", { borowik: 40 }, 0), null);
});

test("loadData: bucket without manifest → no versioned files, pogoda from live/ kept", async () => {
  const B = "https://d.example.pl/";
  globalThis.fetch = mockFetch({ [B + "manifest.json"]: 404, [B + "live/pogoda.json"]: P, [B + "centroidy/index.json"]: IDXC });
  const d = await loadData({ dataBase: B });
  assert.equal(d.manifest.missing, true);
  assert.equal(d.centroidIndex, null);
  assert.equal(d.nazwy, null);
  assert.deepEqual(d.pogoda, P);
});

test("loadData: hanging files → nulls after timeout (page not blocked)", async () => {
  globalThis.fetch = (url) => (url === "data/nazwy.json" ? Promise.resolve({ ok: true, status: 200, json: async () => NZ }) : new Promise(() => {}));
  const t0 = Date.now();
  const d = await loadData({ dataBase: "data/", manifest: LOCAL_MANIFEST, timeoutMs: 30 });
  assert.ok(Date.now() - t0 < 1000);
  assert.equal(d.pogoda, null);
  assert.equal(d.centroidIndex, null);
  assert.deepEqual(d.nazwy, NZ);
});

test("limity czasu: pliki danych 30 s, config/manifest 4 s", () => {
  assert.equal(DATA_TIMEOUT_MS, 30000);
  assert.equal(FETCH_TIMEOUT_MS, 4000);
});


import { GROUP_PREFIX, groupsOf, selectionKeys, isMulti, selectionValues } from "../js/data.js";

const LIST = [{ key: "borowik" }, { key: "kozlarz" }, { key: "kozlarz_czerwony" }, { key: "kurka" }];
const GROUPS = [{ key: "kozlarze", name: "Koźlarze (kozaki)", all: "Wszystkie koźlarze", species: ["kozlarz", "kozlarz_czerwony", "nieznany"] }];

test("selectionKeys: grupa, all, gatunek, nieznane", () => {
  assert.equal(GROUP_PREFIX, "g-");
  assert.deepEqual(selectionKeys("g-kozlarze", LIST, GROUPS), ["kozlarz", "kozlarz_czerwony"]);
  assert.deepEqual(selectionKeys("all", LIST, GROUPS), ["borowik", "kozlarz", "kozlarz_czerwony", "kurka"]);
  assert.deepEqual(selectionKeys("kurka", LIST, GROUPS), ["kurka"]);
  assert.deepEqual(selectionKeys("g-nie", LIST, GROUPS), []);
  assert.deepEqual(selectionKeys("xyz", LIST, GROUPS), []);
});

test("isMulti i selectionValues", () => {
  assert.equal(isMulti("all"), true);
  assert.equal(isMulti("g-kozlarze"), true);
  assert.equal(isMulti("kurka"), false);
  assert.deepEqual(selectionValues(LIST, GROUPS), ["all", "g-kozlarze", "borowik", "kozlarz", "kozlarz_czerwony", "kurka"]);
});

test("groupsOf: brak gatunki.json -> brak grup", () => {
  assert.deepEqual(groupsOf(null), []);
  assert.deepEqual(groupsOf({ groups: GROUPS }), GROUPS);
});
