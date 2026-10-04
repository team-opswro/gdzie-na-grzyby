import test from "node:test";
import assert from "node:assert/strict";
import { AREAS, initialMapView, areaAt } from "../js/areas.js";
import { parseHash, formatHash } from "../js/hash.js";

test("wejście bez linku do miejsca otwiera okolice Wrocławia", () => {
  assert.deepEqual(initialMapView(parseHash("")), { center: [17.033, 51.11], zoom: 10 });
});

test("udostępnione miejsce i zoom mają pierwszeństwo przed Wrocławiem", () => {
  assert.deepEqual(initialMapView(parseHash("#c=50.65,17.9&z=14")), { center: [17.9, 50.65], zoom: 14 });
});

test("Miękinia, Milicz i Twardogóra pozostają wybrane po udostępnieniu linku", () => {
  for (const key of ["miekinia", "milicz", "twardogora"]) {
    const area = AREAS[key];
    const hash = formatHash({ species: "all", day: 0, ...area });
    const view = initialMapView(parseHash(hash));
    assert.deepEqual(view, { center: area.center, zoom: area.zoom });
    assert.equal(areaAt({ lng: view.center[0], lat: view.center[1] }), key);
  }
});

test("ręczne przesunięcie mapy nie pozostawia etykiety innej okolicy", () => {
  assert.equal(areaAt({ lng: 18.5, lat: 50.8 }), "");
});
