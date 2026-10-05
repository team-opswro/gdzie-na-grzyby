import test from "node:test";
import assert from "node:assert/strict";
import { init } from "../js/ui.js";
import { AREAS } from "../js/areas.js";

function element() {
  return {
    children: [], attrs: {}, style: {}, dataset: {}, events: {}, value: "", textContent: "",
    classList: { toggle() {} },
    append(...items) { this.children.push(...items); },
    replaceChildren(...items) { this.children = items; },
    setAttribute(key, value) { this.attrs[key] = value; },
    addEventListener(name, fn) { this.events[name] = fn; },
  };
}

class MapStub {
  constructor(options) { this.center = options.center; this.zoom = options.zoom; this.events = {}; }
  getCenter() { return { lng: this.center[0], lat: this.center[1] }; }
  getZoom() { return this.zoom; }
  getLayer() { return undefined; }
  addControl() {}
  once() {}
  on(name, ...args) { this.events[name] = args.at(-1); }
  jumpTo({ center, zoom }) { this.center = center; this.zoom = zoom; this.events.moveend?.(); }
  flyTo(view) { this.jumpTo(view); }
}

test("wybór Twardogóry przenosi mapę i ranking oraz ignoruje spóźnioną odpowiedź GPS", async () => {
  const keys = ["document", "navigator", "location", "history", "fetch", "maplibregl", "pmtiles"];
  const saved = keys.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]);
  const elements = new Map();
  const node = (id) => {
    if (!elements.has(id)) elements.set(id, element());
    return elements.get(id);
  };
  let gpsSuccess;
  const globals = {
    document: { getElementById: node, createElement: element, querySelectorAll: () => [] },
    navigator: { onLine: true, geolocation: { getCurrentPosition(success) { gpsSuccess = success; } } },
    location: { hash: "", href: "https://example.test/", protocol: "https:" },
    history: { replaceState(_state, _title, hash) { globals.location.hash = hash; } },
    maplibregl: { Map: MapStub, addProtocol() {}, NavigationControl: class {} },
    pmtiles: { Protocol: class { tile() {} } },
    fetch: async (url) => ({
      ok: url === "config.json" || url === "data/manifest.json",
      status: 404,
      json: async () => url === "config.json"
        ? { dataBase: "data/" }
        : { base: "", files: {} },
    }),
  };
  try {
    for (const [key, value] of Object.entries(globals)) {
      Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
    }
    const map = await init();
    assert.deepEqual(map.center, AREAS.wroclaw.center);
    assert.equal(node("area").value, "wroclaw");
    // pierwsze wejście bez hasha: ranking w linii prostej, promień domyślny — lista od razu, bez „Oblicz dojazd”
    assert.equal(node("travel").value, "air");
    assert.equal(node("radius").value, "20");
    assert.equal(node("drive-search").hidden, true);

    node("locate").events.click();
    node("area").value = "twardogora";
    node("area").events.change();
    assert.deepEqual(map.center, AREAS.twardogora.center);
    assert.equal(map.zoom, 12);
    assert.equal(node("ranking-source").textContent, "od środka mapy");
    assert.equal(node("locate").attrs["aria-pressed"], "false");
    assert.equal(node("panel-toggle").attrs["aria-expanded"], "true");
    assert.match(globals.location.hash, /c=51\.365,17\.468/);

    gpsSuccess({ coords: { longitude: 17.9, latitude: 50.65 } });
    assert.deepEqual(map.center, AREAS.twardogora.center);
    assert.equal(node("area").value, "twardogora");

    node("travel").value = "car";
    node("travel").events.change();
    assert.equal(node("drive-search").hidden, false);
    node("drive-search").events.click();
    assert.equal(node("ranking-source").textContent, "od wybranego punktu wyjazdu");
    assert.match(globals.location.hash, /t=car&o=51\.365,17\.468/);
    map.jumpTo({ center: AREAS.miekinia.center, zoom: 12 });
    assert.match(globals.location.hash, /o=51\.365,17\.468/);
    node("drive-start").events.click();
    assert.match(globals.location.hash, /o=51\.192,16\.739/);
  } finally {
    for (const [key, descriptor] of saved) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete globalThis[key];
    }
  }
});
