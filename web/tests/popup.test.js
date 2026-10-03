import { test } from "node:test";
import assert from "node:assert/strict";
import * as popup from "../js/popup.js";
import { reserveText, ZAKAZY_URL } from "../js/popup.js";

test("rankLabel formats grouped place, distance, bearing and count", () => {
  const group = {
    key: "02-04-1-07-368",
    best: { id: "02-04-1-07-368-a-00" },
    count: 3,
    distanceKm: 4.2,
    bearing: "płn.-wsch.",
  };
  const nazwy = {
    nadl: { "02-04": "Brzeg" },
    lesn: { "02-04-1-07": "Zieleniec" },
  };

  assert.equal(typeof popup.rankLabel, "function");
  assert.deepEqual(popup.rankLabel(group, nazwy), {
    line1: "Oddz. 368 · Leśn. Zieleniec · Nadl. Brzeg",
    line2: "4,2 km płn.-wsch. · 3 wydz.",
  });
});

test("reserveText with and without name", () => {
  assert.equal(reserveText("Góra Św. Anny"),
    "Rezerwat przyrody „Góra Św. Anny” — zbieranie grzybów jest co do zasady zabronione.");
  assert.equal(reserveText("rezerwat"),
    "Rezerwat przyrody — zbieranie grzybów jest co do zasady zabronione.");
});
test("zakazy URL", () => assert.equal(ZAKAZY_URL, "https://zakazywstepu.bdl.lasy.gov.pl/zakazy/"));

import { LIM_TEXT, moistureLabel, formatWx, trendArrow, trendLabel } from "../js/popup.js";

test("LIM_TEXT exact", () => assert.deepEqual(LIM_TEXT, {
  dry: "Ogranicza: za mało deszczu",
  dry_soil: "Ogranicza: przesuszona gleba",
  cold: "Ogranicza: za zimna gleba",
  hot: "Ogranicza: za ciepła gleba",
  season: "Ogranicza: poza sezonem",
}));
test("moistureLabel", () => {
  assert.equal(moistureLabel(0.149), "sucha");
  assert.equal(moistureLabel(0.15), "umiarkowana");
  assert.equal(moistureLabel(0.30), "wilgotna");
});
test("formatWx", () => assert.deepEqual(formatWx({ rain_mm: 34.2, soil_t: 11.3, soil_m: 0.31 }), {
  rain: "Deszcz (5–21 dni wcześniej): 34,2 mm",
  soil: "Gleba: 11,3 °C, wilgotna",
}));
test("trendArrow", () => {
  assert.equal(trendArrow("up"), "↑");
  assert.equal(trendArrow("down"), "↓");
  assert.equal(trendArrow("flat"), "→");
  assert.equal(trendArrow(null), "");
});

test("trendLabel", () => {
  assert.equal(trendLabel({ dir: "up", delta: 12 }), "rośnie, +12");
  assert.equal(trendLabel({ dir: "down", delta: -7 }), "spada, -7");
  assert.equal(trendLabel({ dir: "flat", delta: 2 }), "bez zmian, +2");
  assert.equal(trendLabel({ dir: null, delta: 0 }), "");
});
