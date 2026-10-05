import test from "node:test";
import assert from "node:assert/strict";
import { createDrivePlanner, driveSettings, drivingUrl } from "../js/driving.js";
import { parseHash, formatHash } from "../js/hash.js";

const origin = { lat: 51.11, lon: 17.033 };
const candidate = (i) => ({ key: String(i), best: { id: String(i), lat: 51.12, lon: 17.04 + i / 10000, score: 100 - i } });
const parking = (i) => ({ id: String(i), lat: 51.12, lon: 17.04 + i / 10000, forestDistanceKm: 0.5 });
const nearby = { near: async (p) => [parking(Number(p.id))] };

function tableResponse(distances, { durations = distances.map(() => 1800), snap = distances.map(() => 0), sourceSnap = 0 } = {}) {
  return { ok: true, json: async () => ({ code: "Ok", sources: [{ distance: sourceSnap }], destinations: snap.map((distance) => ({ distance })), distances: [distances], durations: [durations] }) };
}

test("limit 50 km sprawdza niezaokrąglone kilometry drogi, nie odległość w linii prostej", async () => {
  const planner = createDrivePlanner(nearby, { intervalMs: 0, fetcher: async () => tableResponse([50001, 50000, 32000]) });
  const { results } = await planner.find([candidate(0), candidate(1), candidate(2)], origin, 50);
  assert.deepEqual(results.map((r) => r.key), ["1", "2"]);
  assert.equal(results[0].drive.meters, 50000);
});

test("szukanie trwa także po odrzuceniu pierwszych dziesięciu najlepiej ocenionych miejsc", async () => {
  let calls = 0;
  const planner = createDrivePlanner(nearby, { intervalMs: 0, fetcher: async () => tableResponse(Array(10).fill(++calls === 1 ? 60000 : 30000)) });
  const { results } = await planner.find(Array.from({ length: 20 }, (_, i) => candidate(i)), origin, 50);
  assert.equal(calls, 2);
  assert.deepEqual(results.map((r) => r.key), Array.from({ length: 10 }, (_, i) => String(i + 10)));
});

test("brak trasy i parking odległy od dopasowanej drogi są pomijane", async () => {
  const planner = createDrivePlanner(nearby, { intervalMs: 0, fetcher: async () => tableResponse([null, 30000, 25000], { snap: [0, 101, 0] }) });
  const { results } = await planner.find([candidate(0), candidate(1), candidate(2)], origin, 50);
  assert.deepEqual(results.map((r) => r.key), ["2"]);
});

test("wybierany jest krótszy potwierdzony dojazd spośród parkingów przy miejscu", async () => {
  const parkings = { near: async () => [parking(0), parking(1), parking(2)] };
  const planner = createDrivePlanner(parkings, { intervalMs: 0, fetcher: async () => tableResponse([51000, 35000, 42000]) });
  const { results } = await planner.find([candidate(0)], origin, 50);
  assert.equal(results[0].drive.parking.id, "1");
});

test("cache tras nie myli odległości od parkingu dla różnych wydzieleń", async () => {
  let calls = 0;
  const parks = { near: async (p) => [{ ...parking(0), forestDistanceKm: Number(p.id) / 10 }] };
  const planner = createDrivePlanner(parks, { intervalMs: 0, fetcher: async () => { calls++; return tableResponse([25000]); } });
  const one = await planner.find([candidate(1)], origin, 50);
  const two = await planner.find([candidate(7)], origin, 50);
  assert.equal(calls, 1);
  assert.equal(one.results[0].drive.parking.forestDistanceKm, 0.1);
  assert.equal(two.results[0].drive.parking.forestDistanceKm, 0.7);
  await planner.find([candidate(7)], { ...origin, lon: 17.034 }, 50);
  assert.equal(calls, 2);
});

test("awaria usługi nie powoduje zastąpienia kilometrów drogi odległością w linii prostej", async () => {
  const planner = createDrivePlanner(nearby, { intervalMs: 0, fetcher: async () => { throw new Error("network"); } });
  await assert.rejects(planner.find([candidate(0)], origin, 50), /network/);
});

test("brak parkingu pomija miejsce bez wywoływania routingu", async () => {
  const planner = createDrivePlanner({ near: async () => [] }, { fetcher: () => { throw new Error("should not fetch"); } });
  assert.deepEqual((await planner.find([candidate(0)], origin, 50)).results, []);
});

test("nieaktualne wyszukiwanie jest zatrzymywane przed żądaniem dojazdu", async () => {
  const planner = createDrivePlanner(nearby, { fetcher: () => { throw new Error("should not fetch"); } });
  const result = await planner.find([candidate(0)], origin, 50, { current: () => false });
  assert.equal(result.cancelled, true);
});

test("ograniczenie liczby sprawdzonych kandydatów jest jawnie zgłaszane", async () => {
  const planner = createDrivePlanner({ near: async () => [] });
  const result = await planner.find(Array.from({ length: 201 }, (_, i) => candidate(i)), origin, 50);
  assert.equal(result.checked, 200);
  assert.equal(result.limited, true);
});

test("kolejne partie przestrzegają minimalnego odstępu zapytań", async () => {
  const times = [];
  const planner = createDrivePlanner(nearby, { intervalMs: 25, fetcher: async () => { times.push(Date.now()); return tableResponse(Array(10).fill(60000)); } });
  await planner.find(Array.from({ length: 20 }, (_, i) => candidate(i)), origin, 50);
  assert.ok(times[1] - times[0] >= 25);
});

test("link zachowuje tryb samochodowy, 50 km i przybliżony punkt wyjazdu", () => {
  const hash = formatHash({ species: "all", day: 0, radius: 50, travel: "car", driveOrigin: origin });
  assert.equal(parseHash(hash).radius, 50);
  assert.deepEqual(driveSettings(hash), { mode: "car", origin });
  assert.equal(driveSettings("").mode, "air");  // pierwsze wejście: ranking od razu, bez dojazdu
  assert.equal(driveSettings("#s=all&r=40").mode, "air");
  assert.equal(driveSettings("#t=car&o=999,999").origin, null);
  assert.equal(driveSettings("#t=car&o=,").origin, null);
  assert.match(drivingUrl(origin, parking(1)), /origin=51\.11,17\.033/);
  assert.match(drivingUrl(origin, parking(1)), /travelmode=driving/);
});
