import test from "node:test";
import assert from "node:assert/strict";
import { normalizeBase, loadConfig, loadManifest, fileUrl, pogodaUrl, getJson, LOCAL_MANIFEST } from "../js/config.js";

const res = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });
function mockFetch(map) {
  const calls = [];
  const f = async (url) => {
    calls.push(url);
    const r = map[url];
    if (r === undefined || r === "throw") throw new Error("net");
    if (typeof r === "number") return res(null, r);
    return res(r);
  };
  f.calls = calls;
  return f;
}

test("normalizeBase: trailing slash, empty → data/", () => {
  assert.equal(normalizeBase("https://d.example.pl"), "https://d.example.pl/");
  assert.equal(normalizeBase("https://d.example.pl/"), "https://d.example.pl/");
  assert.equal(normalizeBase("  https://d.example.pl/x  "), "https://d.example.pl/x/");
  assert.equal(normalizeBase(""), "data/");
  assert.equal(normalizeBase(null), "data/");
  assert.equal(normalizeBase(undefined), "data/");
  assert.equal(normalizeBase(42), "data/");
});

test("loadConfig reads dataBase from config.json", async () => {
  const f = mockFetch({ "config.json": { dataBase: "https://d.example.pl" } });
  assert.deepEqual(await loadConfig(f), { dataBase: "https://d.example.pl/" });
  assert.deepEqual(f.calls, ["config.json"]);
});

test("loadConfig fallback data/ on 404, network error, bad shape", async () => {
  for (const r of [404, "throw", {}, { dataBase: "" }, "x"]) {
    assert.deepEqual(await loadConfig(mockFetch({ "config.json": r })), { dataBase: "data/" });
  }
});

const M = {
  build: "20261003-1200-abcdef1", base: "v/20261003-1200-abcdef1/", generated_at: "2026-10-03T12:00:00Z",
  files: { lasy: "lasy.pmtiles", centroidy: "centroidy/index.json", grid: "grid.json", nazwy: "nazwy.json", gatunki: "gatunki.json" },
};

test("loadManifest reads manifest.json from dataBase", async () => {
  const f = mockFetch({ "https://d.example.pl/manifest.json": M });
  assert.deepEqual(await loadManifest("https://d.example.pl/", f), M);
});

test("loadManifest: data/ without manifest → files in data/ root (base '')", async () => {
  for (const r of [404, "throw", { files: null }]) {
    const m = await loadManifest("data/", mockFetch({ "data/manifest.json": r }));
    assert.equal(m, LOCAL_MANIFEST);
    assert.equal(m.base, "");
    assert.equal(fileUrl("data/", m, "centroidy"), "data/centroidy/index.json");
    assert.equal(fileUrl("data/", m, "lasy"), "data/lasy.pmtiles");
  }
});

test("fileUrl joins dataBase + base + file; unknown key → null", () => {
  assert.equal(fileUrl("https://d.example.pl/", M, "lasy"), "https://d.example.pl/v/20261003-1200-abcdef1/lasy.pmtiles");
  assert.equal(fileUrl("https://d.example.pl/", M, "nope"), null);
  assert.equal(fileUrl("https://d.example.pl/", null, "lasy"), null);
});

test("pogodaUrl is live/pogoda.json outside the version", () => {
  assert.equal(pogodaUrl("https://d.example.pl/"), "https://d.example.pl/live/pogoda.json");
  assert.equal(pogodaUrl("data/"), "data/live/pogoda.json");
});

const hang = () => new Promise(() => {});

test("loadConfig: hanging config.json → data/ after timeout", async () => {
  const t0 = Date.now();
  assert.deepEqual(await loadConfig(hang, 30), { dataBase: "data/" });
  assert.ok(Date.now() - t0 < 1000);
});

test("loadManifest: hanging manifest on bucket → missing after timeout, no files", async () => {
  const m = await loadManifest("https://d.example.pl/", hang, 30);
  assert.equal(m.missing, true);
  assert.equal(fileUrl("https://d.example.pl/", m, "lasy"), null);
  assert.equal(fileUrl("https://d.example.pl/", m, "centroidy"), null);
});

test("loadManifest: hanging manifest in data/ → LOCAL_MANIFEST", async () => {
  assert.equal(await loadManifest("data/", hang, 30), LOCAL_MANIFEST);
});

test("loadManifest: bucket without manifest (404/net/bad shape) → missing, no root fallback", async () => {
  for (const r of [404, "throw", { files: null }]) {
    const m = await loadManifest("https://d.example.pl/", mockFetch({ "https://d.example.pl/manifest.json": r }));
    assert.equal(m.missing, true);
    assert.notEqual(m, LOCAL_MANIFEST);
  }
  assert.equal(LOCAL_MANIFEST.missing, undefined);
});

test("getJson aborts the request signal on timeout", async () => {
  let signal;
  const f = (url, opts) => { signal = opts.signal; return hang(); };
  await assert.rejects(getJson(f, "x.json", 20), /timeout/);
  assert.equal(signal.aborted, true);
});
