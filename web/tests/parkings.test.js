import test from "node:test";
import assert from "node:assert/strict";
import { decodeParkings, createParkingStore, parkingTiles } from "../js/parkings.js";

const vint = (n) => {
  const bytes = [];
  do { const next = n % 128; n = Math.floor(n / 128); bytes.push(next + (n ? 128 : 0)); } while (n);
  return Buffer.from(bytes);
};
const bytes = (field, value) => Buffer.concat([vint(field * 8 + 2), vint(value.length), value]);
const integer = (field, value) => Buffer.concat([vint(field * 8), vint(value)]);
const string = (field, value) => bytes(field, Buffer.from(value));

function tile() {
  const feature = Buffer.concat([
    bytes(2, Buffer.from([0, 0, 1, 1, 2, 2])), integer(3, 1),
    bytes(4, Buffer.concat([vint(9), vint(4096), vint(4096)])),
  ]);
  const layer = Buffer.concat([
    integer(15, 2), string(1, "parkingi"), bytes(2, feature),
    ...["osm", "name", "fee"].map((key) => string(3, key)),
    ...["n42", "Parking Leśny", "yes"].map((value) => bytes(4, string(1, value))),
    integer(5, 4096),
  ]);
  return Buffer.concat([bytes(3, Buffer.concat([string(1, "lasy"), integer(15, 2)])), bytes(3, layer)]);
}

test("MVT: parkingi mają poprawne współrzędne, nazwę i opłatę; warstwa lasów jest pomijana", () => {
  const result = decodeParkings(tile(), 11, 1119, 683);
  assert.equal(result.length, 1);
  assert.equal(result[0].id, "n42");
  assert.equal(result[0].name, "Parking Leśny");
  assert.equal(result[0].fee, "yes");
  assert.ok(result[0].lat > 51 && result[0].lat < 51.3);
  assert.ok(Math.abs(result[0].lon - 16.787109375) < 1e-10);
});

test("uszkodzony protobuf parkingów zgłasza błąd", () => {
  assert.throws(() => decodeParkings(Buffer.from([26, 127]), 11, 1119, 683), /Niepełny/);
  assert.throws(() => decodeParkings(Buffer.from([128]), 11, 1119, 683), /Nieprawidłowy/);
});

test("odczyt parkingów korzysta z cache kafelków i pomija punkty poza 1,5 km", async () => {
  const point = decodeParkings(tile(), 11, 1119, 683)[0];
  let calls = 0;
  const store = createParkingStore({ getZxy: async (_z, x, y) => { calls++; return x === 1119 && y === 683 ? { data: tile() } : undefined; } });
  const first = await store.near(point);
  const count = calls;
  const second = await store.near(point);
  assert.equal(calls, count);
  assert.deepEqual(first, second);
  assert.equal(first.length, 1);
  assert.ok(first[0].forestDistanceKm < 1e-6);
  assert.deepEqual(await store.near({ lat: 51.8, lon: 18 }), []);
  assert.ok(parkingTiles(point).every(([z]) => z === 11));
});

test("nieudane pobranie jest ponawiane zamiast zapisywania pustego parkingu w cache", async () => {
  const point = decodeParkings(tile(), 11, 1119, 683)[0];
  let fail = true;
  const store = createParkingStore({ getZxy: async () => {
    if (fail) { fail = false; throw new Error("network"); }
    return { data: tile() };
  } });
  await assert.rejects(store.near(point), /network/);
  const found = await store.near(point);
  assert.equal(found.length, 1);
});

test("wiszące pobranie parkingów kończy się błędem", async () => {
  const store = createParkingStore({ getZxy: () => new Promise(() => {}) }, { timeoutMs: 10 });
  await assert.rejects(store.near({ lat: 51.192, lon: 16.739 }), /czas pobierania/);
});
