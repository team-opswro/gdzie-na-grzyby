// Test zachowania web/sw.js w atrapie środowiska service workera (Cache API zużywa body jak w przeglądarce).
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const read = (f) => fs.readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
const CORE = read("sw-core.js");
const SW = read("sw.js");

class FakeCache {
  constructor() { this.entries = new Map(); }
  async match(req) {
    const e = this.entries.get(typeof req === "string" ? req : req.url);
    return e ? new Response(e.body.slice(0), { status: e.status, headers: e.headers }) : undefined;
  }
  async put(req, resp) {
    if (resp.bodyUsed) throw new TypeError("body już odczytane");
    const body = await resp.arrayBuffer(); // jak w przeglądarce: put zużywa body
    this.entries.set(typeof req === "string" ? req : req.url, { body, status: resp.status, headers: new Headers(resp.headers) });
  }
  async keys() {
    await new Promise((r) => setTimeout(r, 5)); // Cache API to I/O — odpowiada asynchronicznie
    return [...this.entries.keys()].map((url) => ({ url }));
  }
  async delete(req) { return this.entries.delete(typeof req === "string" ? req : req.url); }
}

function loadWorker(fetchImpl, scope = "https://app.example/") {
  const stores = new Map();
  const handlers = {};
  const caches = {
    async open(name) { if (!stores.has(name)) stores.set(name, new FakeCache()); return stores.get(name); },
    async keys() { return [...stores.keys()]; },
    async delete(name) { return stores.delete(name); },
  };
  const self = {
    registration: { scope },
    clients: { claim: async () => {} },
    skipWaiting: async () => {},
    addEventListener: (type, fn) => { handlers[type] = fn; },
  };
  const ctx = vm.createContext({
    self, caches, fetch: fetchImpl, Response, Request, Headers, URL, AbortController,
    setTimeout, clearTimeout, Promise, console,
  });
  ctx.importScripts = () => vm.runInContext(CORE, ctx);
  vm.runInContext(SW, ctx);
  const dispatch = (request) => {
    let p = null;
    handlers.fetch({ request, respondWith: (x) => { p = x; } });
    return p;
  };
  return { dispatch, stores };
}

const PM = "https://app.example/dane/v/b1/lasy.pmtiles";
const bytes = (s) => new TextEncoder().encode(s);

function rangeServer() {
  const calls = [];
  const fetchImpl = async (req) => {
    calls.push(req.url);
    const r = req.headers.get("Range");
    if (r) return new Response(bytes(`ZAKRES ${r}`), { status: 206, headers: { "Content-Range": `bytes 0-9/100` } });
    return new Response(bytes("CAŁOŚĆ"), { status: 200 });
  };
  return { calls, fetchImpl };
}

test("sw: pierwsze żądanie Range (brak w cache) zwraca 206 z treścią i zapisuje wpis", async () => {
  const { calls, fetchImpl } = rangeServer();
  const { dispatch, stores } = loadWorker(fetchImpl);
  const resp = await dispatch(new Request(PM, { headers: { Range: "bytes=0-9" } }));
  assert.equal(resp.status, 206);
  assert.equal(resp.headers.get("Content-Range"), "bytes 0-9/100");
  assert.equal(await resp.text(), "ZAKRES bytes=0-9");
  const again = await dispatch(new Request(PM, { headers: { Range: "bytes=0-9" } }));
  assert.equal(await again.text(), "ZAKRES bytes=0-9");
  assert.equal(calls.length, 1); // drugie z cache
  assert.equal(stores.get("grzyby-data").entries.size, 1);
});

test("sw: różne zakresy to różne wpisy", async () => {
  const { fetchImpl } = rangeServer();
  const { dispatch } = loadWorker(fetchImpl);
  await (await dispatch(new Request(PM, { headers: { Range: "bytes=0-9" } }))).text();
  await (await dispatch(new Request(PM, { headers: { Range: "bytes=10-19" } }))).text();
  const a = await dispatch(new Request(PM, { headers: { Range: "bytes=0-9" } }));
  const b = await dispatch(new Request(PM, { headers: { Range: "bytes=10-19" } }));
  assert.equal(await a.text(), "ZAKRES bytes=0-9");
  assert.equal(await b.text(), "ZAKRES bytes=10-19");
});

test("sw: kafel podkładu trafia do cache, nawet gdy strona od razu czyta odpowiedź", async () => {
  const fetchImpl = async () => new Response(bytes("PNG"), { status: 200 });
  const { dispatch, stores } = loadWorker(fetchImpl);
  const resp = await dispatch(new Request("https://tile.openstreetmap.org/12/1/1.png"));
  assert.equal(await resp.text(), "PNG"); // strona zużywa body
  await new Promise((r) => setTimeout(r, 20));
  assert.equal(stores.get("grzyby-base").entries.size, 1);
});

test("sw: nowy build danych usuwa wpisy starych buildów z grzyby-data", async () => {
  const { fetchImpl } = rangeServer();
  const { dispatch, stores } = loadWorker(fetchImpl);
  await (await dispatch(new Request(PM, { headers: { Range: "bytes=0-9" } }))).text();
  await (await dispatch(new Request(PM.replace("/b1/", "/b2/"), { headers: { Range: "bytes=0-9" } }))).text();
  const keys = [...stores.get("grzyby-data").entries.keys()];
  assert.equal(keys.length, 1);
  assert.ok(keys[0].includes("/v/b2/"));
});
