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

test("rankLabel w trybie all dopisuje krótką nazwę gatunku", () => {
  const g = { key: "k", best: { id: "02-04-1-07-368-a-00" }, count: 1, distanceKm: 1, bearing: "płn.", species: "kozlarz" };
  const l = popup.rankLabel(g, null, [{ key: "kozlarz", name: "Koźlarz babka" }]);
  assert.ok(l.line1.endsWith(" · koźlarz"));
  assert.equal(popup.shortName("Borowik szlachetny"), "borowik");
});

import fs from "node:fs";
import { installDom, walk } from "./dom-stub.js";

test("renderPopup w trybie all: bez pogody i ze starą pogodą — paski gatunków, bez wyjątku", () => {
  installDom();
  const P = JSON.parse(fs.readFileSync(new URL("../../tests/fixtures/pogoda.json", import.meta.url), "utf8"));
  const old = { ...P, wx: undefined };
  for (const s of old.days ? Object.values(old.cells) : []) for (const k of Object.keys(s)) delete s[k].lim;
  const props = { id: "x", cell: "506_178", h_borowik: 80, h_podgrzybek: 50, h_kurka: 40, h_kozlarz: 30, h_maslak: 20, h_rydz: 10 };
  for (const pg of [null, old]) {
    const root = popup.renderPopup(props, { pogoda: pg, species: "all", dayIdx: 0, todayIso: P.days[0] });
    let items = 0;
    walk(root, (n) => { if (n.tag === "li") items++; });
    assert.equal(items, 6);
  }
});

test("renderPopup w trybie all: plakietka wyniku z krótką nazwą gatunku", () => {
  installDom();
  const P = JSON.parse(fs.readFileSync(new URL("../../tests/fixtures/pogoda.json", import.meta.url), "utf8"));
  const props = { id: "x", cell: "506_178", h_borowik: 80, h_podgrzybek: 50, h_kurka: 40, h_kozlarz: 30, h_maslak: 20, h_rydz: 10 };
  const root = popup.renderPopup(props, { pogoda: P, species: "all", dayIdx: 0, todayIso: P.days[0] });
  let text = null;
  walk(root, (n) => { if (n.className === "popup-score") text = (n.children ?? []).map((c) => c.textContent ?? c).join(""); });
  assert.match(String(text), /^Wynik: \d+\/100 \([^)]+\) · [a-ząćęłńóśźż]+/);
});

test("popup: brak atrybutu h_* = 0 (zerowe h nie są zapisywane w kafelkach)", () => {
  installDom();
  const root = popup.renderPopup({ id: "x", cell: "506_178", sp: "OL" }, { pogoda: null, species: "borowik", dayIdx: 0 });
  const cells = [];
  walk(root, (n) => { if (n.tag === "td" || n.tag === "th") cells.push(String(n.textContent ?? "")); });
  const i = cells.indexOf("Siedlisko");
  assert.ok(i >= 0);
  assert.equal(cells[i + 1], "0%");
});
