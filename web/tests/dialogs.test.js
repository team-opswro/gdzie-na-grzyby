import test from "node:test";
import assert from "node:assert/strict";
import { speciesCardModel, aboutForecastText, RISK_COLORS, DISCLAIMER, UNREVIEWED_TEXT, NO_INFO_TEXT } from "../js/dialogs.js";

const info = {
  reviewed: false,
  species: [{
    key: "borowik", name: "Borowik szlachetny", latin: "Boletus edulis",
    season: { start: "07-01", end: "10-31" },
    partners: ["sosna", "świerk"], habitats_preferred: ["bór świeży"], habitats_adjacent: ["bór wilgotny"],
    age_min: 30, description: "Opis.", lookalikes: [{ name: "Goryczak żółciowy", latin: "Tylopilus felleus", risk: "niejadalny", how: "Gorzki." }],
    wiki: "https://pl.wikipedia.org/wiki/Borowik_szlachetny",
  }],
};

test("speciesCardModel", () => {
  const m = speciesCardModel(info, "borowik");
  assert.equal(m.title, "Borowik szlachetny");
  assert.equal(m.latin, "Boletus edulis");
  assert.equal(m.season, "1 lip – 31 paź");
  assert.equal(m.partners, "sosna, świerk");
  assert.equal(m.preferred, "bór świeży");
  assert.equal(m.adjacent, "bór wilgotny");
  assert.equal(m.age, "od 30 lat");
  assert.equal(m.description, "Opis.");
  assert.equal(m.lookalikes.length, 1);
  assert.equal(m.wiki, info.species[0].wiki);
  assert.equal(m.unreviewed, true);
});
test("speciesCardModel reviewed", () => {
  assert.equal(speciesCardModel({ ...info, reviewed: true }, "borowik").unreviewed, false);
});
test("speciesCardModel null cases", () => {
  assert.equal(speciesCardModel(null, "borowik"), null);
  assert.equal(speciesCardModel(info, "all"), null);
  assert.equal(speciesCardModel(info, "nic"), null);
});
test("constants", () => {
  assert.equal(DISCLAIMER, "Nie zbieraj grzybów, których nie znasz. W razie wątpliwości skorzystaj z punktu grzyboznawczego (Sanepid).");
  assert.equal(UNREVIEWED_TEXT, "Opis nie został jeszcze zweryfikowany przez grzyboznawcę.");
  assert.equal(NO_INFO_TEXT, "Brak opisu gatunku");
  assert.deepEqual(RISK_COLORS, { niejadalny: "#fdd835", trujący: "#fb8c00", "śmiertelnie trujący": "#d32f2f" });
});
test("aboutForecastText", () => {
  assert.equal(aboutForecastText(null), "brak prognozy");
  assert.equal(aboutForecastText("nonsense"), "brak prognozy");
  assert.match(aboutForecastText("2026-10-03T03:00:00Z"), /^Prognoza z: \d{1,2} paź, \d{2}:\d{2}$/);
});
