import test from "node:test";
import assert from "node:assert/strict";
import { parseHash, formatHash, BASEMAP_KEYS } from "../js/hash.js";

test("parseHash full", () =>
  assert.deepEqual(parseHash("#s=kurka&d=2&z=11&c=50.67,17.93"), { species: "kurka", day: 2, zoom: 11, center: [17.93, 50.67], basemap: "osm", radius: 20, place: undefined }));
test("parseHash invalid species / day → defaults", () => {
  const r = parseHash("#s=muchomor&d=-3");
  assert.equal(r.species, "borowik");
  assert.equal(r.day, 0);
  assert.equal(r.zoom, undefined);
  assert.equal(r.center, undefined);
  assert.deepEqual(parseHash(""), { species: "borowik", day: 0, zoom: undefined, center: undefined, basemap: "osm", radius: 20, place: undefined });
  assert.equal(parseHash("#d=abc").day, 0);
});
test("roundtrip + rounding", () => {
  const s = { species: "rydz", day: 3, zoom: 10.5, center: [17.93, 50.67], basemap: "osm", radius: 20, place: undefined };
  assert.deepEqual(parseHash(formatHash(s)), s);
  assert.equal(formatHash(s), "#s=rydz&d=3&z=10.5&c=50.67,17.93");
  assert.equal(formatHash({ species: "kurka", day: 0, zoom: 11.123456, center: [17.1234567, 50.7654321] }),
    "#s=kurka&d=0&z=11.12&c=50.76543,17.12346");
  assert.equal(formatHash({ species: "kurka", day: 1 }), "#s=kurka&d=1");
});
test("basemap param", () => {
  assert.equal(parseHash("#s=kurka&d=0&b=orto").basemap, "orto");
  assert.equal(parseHash("#b=satelita").basemap, "osm");
  assert.equal(formatHash({ species: "kurka", day: 0, basemap: "topo" }), "#s=kurka&d=0&b=topo");
  assert.equal(formatHash({ species: "kurka", day: 0, basemap: "osm" }), "#s=kurka&d=0");
});
test("radius and place params", () => {
  const r = parseHash("#r=10&w=02-04-1-07-368-a-00");
  assert.equal(r.radius, 10);
  assert.equal(r.place, "02-04-1-07-368-a-00");
  assert.equal(parseHash("#r=7").radius, 20);
  assert.equal(parseHash("#r=").radius, 20);
  assert.equal(parseHash("#w=<script>").place, undefined);
  assert.equal(parseHash("#w=").place, undefined);
});
test("formatHash radius/place order and roundtrip", () => {
  assert.equal(formatHash({ species: "kurka", day: 0, radius: 20 }), "#s=kurka&d=0");
  const s = { species: "rydz", day: 1, zoom: 15, center: [17.93, 50.67], basemap: "topo", radius: 40, place: "02-04-1-07-368-a-00" };
  assert.equal(formatHash(s), "#s=rydz&d=1&z=15&c=50.67,17.93&b=topo&r=40&w=02-04-1-07-368-a-00");
  assert.deepEqual(parseHash(formatHash(s)), s);
  assert.equal(formatHash({ species: "kurka", day: 0, place: "<x>" }), "#s=kurka&d=0");
  assert.equal(formatHash({ species: "kurka", day: 0, radius: 7 }), "#s=kurka&d=0");
});
