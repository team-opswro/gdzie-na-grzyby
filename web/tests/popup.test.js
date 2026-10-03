import { test } from "node:test";
import assert from "node:assert/strict";
import { reserveText, ZAKAZY_URL } from "../js/popup.js";

test("reserveText with and without name", () => {
  assert.equal(reserveText("Góra Św. Anny"),
    "Rezerwat przyrody „Góra Św. Anny” — zbieranie grzybów jest co do zasady zabronione.");
  assert.equal(reserveText("rezerwat"),
    "Rezerwat przyrody — zbieranie grzybów jest co do zasady zabronione.");
});
test("zakazy URL", () => assert.equal(ZAKAZY_URL, "https://zakazywstepu.bdl.lasy.gov.pl/zakazy/"));

import { LIM_TEXT, moistureLabel, formatWx, trendArrow } from "../js/popup.js";

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
