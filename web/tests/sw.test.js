import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const corePath = path.join(__dirname, "..", "sw-core.js");
const coreSrc = fs.readFileSync(corePath, "utf8");

function loadCore(scope = "https://example.com/") {
  const self = {};
  vm.runInNewContext(coreSrc, { self, URL, Array, String, Number, Object, RegExp, Error });
  return { self, core: self.SWCore, scope };
}

function strat(url, method = "GET", scope = "https://example.com/") {
  const { core } = loadCore(scope);
  return core.strategyFor(url, method, scope);
}

test("strategyFor: pogoda network-first w trybach data/, /dane/ i bucket", () => {
  for (const base of ["https://d.example.com/data/", "https://d.example.com/dane/", "https://bucket.example.com/"]) {
    assert.equal(strat(base + "live/pogoda.json"), "network-first", base);
    assert.equal(strat(base + "config.json"), "network-first", base);
    assert.equal(strat(base + "manifest.json"), "network-first", base);
  }
});

test("strategyFor: pliki wersji cache-first, podkład swr, POST pass, nieznane pass", () => {
  assert.equal(strat("https://d.example.com/v/b1/lasy.pmtiles"), "cache-first");
  assert.equal(strat("https://d.example.com/v/b1/centroidy.json"), "cache-first");
  assert.equal(strat("https://tile.openstreetmap.org/12/2275/1387.png"), "swr");
  assert.equal(strat("https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/StandardResolution?x=1"), "swr");
  assert.equal(strat("https://example.com/api/x", "POST"), "pass");
  assert.equal(strat("https://example.com/unknown"), "pass");
});

test("strategyFor: powłoka network-first (nowe wdrożenie widać od razu), także wejście na /", () => {
  const scope = "https://example.com/";
  assert.equal(strat(scope), "network-first");
  assert.equal(strat(scope + "index.html"), "network-first");
  assert.equal(strat(scope + "js/ui.js"), "network-first");
  assert.equal(strat(scope + "vendor/pmtiles.js"), "network-first");
  assert.equal(strat(scope + "manifest.webmanifest"), "network-first");
  assert.equal(strat(scope + "icons/icon.svg"), "network-first");
  assert.equal(strat("https://example.com/app/", "GET", "https://example.com/app/"), "network-first");
});

test("cacheKey z Range i bez", () => {
  const { core } = loadCore();
  assert.equal(core.cacheKey("https://x/a"), "https://x/a");
  // Cache API pomija fragment (#) przy dopasowaniu — zakres musi być w zapytaniu, inaczej zakresy się nadpisują
  assert.equal(core.cacheKey("https://x/a", "bytes=0-100"), "https://x/a?__range=bytes%3D0-100");
  assert.equal(core.cacheKey("https://x/a?v=1", "bytes=5-9"), "https://x/a?v=1&__range=bytes%3D5-9");
  assert.ok(!core.cacheKey("https://x/a", "bytes=0-100").includes("#"));
  assert.equal(core.cacheKey("https://x/a", null), "https://x/a");
});

test("trimPlan usuwa najstarsze ponad limit", () => {
  const { core } = loadCore();
  const keys = Array.from({ length: 3005 }, (_, i) => `k${i}`);
  const removed = core.trimPlan(keys, 3000);
  assert.equal(removed.length, 5);
  assert.deepEqual(removed, ["k0", "k1", "k2", "k3", "k4"]);
  assert.equal(core.trimPlan(keys.slice(0, 3000), 3000).length, 0);
  assert.equal(core.trimPlan(["a", "b"], 3000).length, 0);
});

test("staleShellCaches nie rusza danych i podkładu", () => {
  const { core } = loadCore();
  const names = ["grzyby-shell-1", "grzyby-shell-2", "grzyby-data", "grzyby-base"];
  const stale = core.staleShellCaches(names);
  assert.ok(stale.every((n) => n.startsWith("grzyby-shell-")));
  assert.ok(!stale.includes(core.SHELL_CACHE));
  assert.ok(!stale.includes("grzyby-data"));
  assert.ok(!stale.includes("grzyby-base"));
  assert.equal(core.staleShellCaches(["grzyby-data", "grzyby-base"]).length, 0);
  assert.equal(core.staleShellCaches([core.SHELL_CACHE]).length, 0);
});

test("SHELL_FILES istnieją na dysku", () => {
  const { core } = loadCore();
  const webDir = path.join(__dirname, "..");
  for (const f of core.SHELL_FILES) {
    const p = path.join(webDir, f);
    assert.ok(fs.existsSync(p), `brak pliku powłoki: ${f}`);
  }
});
