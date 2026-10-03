import test from "node:test";
import assert from "node:assert/strict";
import { oddzKey, placeName, formatPlace, navUrls } from "../js/names.js";

const N = { nadl: { "02-04": "Brzeg" }, lesn: { "02-04-1-07": "Zieleniec" } };

test("oddzKey", () => {
  assert.equal(oddzKey("02-04-1-07-368-a-00"), "02-04-1-07-368");
  assert.equal(oddzKey("06-01-2-13-201B-b-00"), "06-01-2-13-201B");
  assert.equal(oddzKey("x"), null);
});
test("placeName", () => {
  assert.deepEqual(placeName("02-04-1-07-368-a-00", N), { oddz: "368", lesn: "Zieleniec", nadl: "Brzeg", lesnKey: "02-04-1-07" });
  assert.deepEqual(placeName("06-01-2-13-201B-b-00", null), { oddz: "201B", lesn: null, nadl: null, lesnKey: "06-01-2-13" });
});
test("formatPlace", () => {
  assert.equal(formatPlace("02-04-1-07-368-a-00", N), "Oddz. 368 · Leśn. Zieleniec · Nadl. Brzeg");
  assert.equal(formatPlace("02-04-1-07-368-a-00", { nadl: N.nadl, lesn: {} }), "Oddz. 368 · Nadl. Brzeg");
  assert.equal(formatPlace("02-04-1-07-368-a-00", null), "Oddz. 368 · 02-04-1-07");
});
test("navUrls", () => {
  assert.deepEqual(navUrls(50.123456, 17.9), {
    google: "https://www.google.com/maps/dir/?api=1&destination=50.12346,17.90000",
    osm: "https://www.openstreetmap.org/directions?route=%3B50.12346%2C17.90000",
  });
});
