import test from "node:test";
import assert from "node:assert/strict";
import { installDom } from "./dom-stub.js";
import { buildSpeciesOptions } from "../js/select.js";

const LIST = [
  { key: "borowik", name: "Borowik szlachetny", group: "borowiki" },
  { key: "kurka", name: "Kurka", group: null },
  { key: "kozlarz", name: "Koźlarz babka", group: "kozlarze" },
  { key: "borowik_sosnowy", name: "Borowik sosnowy", group: "borowiki" },
  { key: "kozlarz_czerwony", name: "Koźlarz czerwony", group: "kozlarze" },
];
const GROUPS = [
  { key: "borowiki", name: "Borowiki", all: "Wszystkie borowiki", species: ["borowik", "borowik_sosnowy"] },
  { key: "kozlarze", name: "Koźlarze (kozaki)", all: "Wszystkie koźlarze", species: ["kozlarz", "kozlarz_czerwony"] },
];

function sel() {
  installDom();
  return document.createElement("select");
}

test("buildSpeciesOptions: optgroup na grupę + Inne", () => {
  const s = sel();
  buildSpeciesOptions(s, LIST, GROUPS);
  const [first, ...groups] = s.children;
  assert.equal(first.tag, "option");
  assert.equal(first.value, "all");
  assert.equal(first.textContent, "Wszystkie gatunki");
  assert.deepEqual(groups.map((g) => [g.tag, g.label]),
    [["optgroup", "Borowiki"], ["optgroup", "Koźlarze (kozaki)"], ["optgroup", "Inne"]]);
  const koz = groups[1].children.map((o) => [o.value, o.textContent]);
  assert.deepEqual(koz, [["g-kozlarze", "Wszystkie koźlarze"], ["kozlarz", "Koźlarz babka"], ["kozlarz_czerwony", "Koźlarz czerwony"]]);
  assert.deepEqual(groups[2].children.map((o) => o.value), ["kurka"]);
});

test("buildSpeciesOptions: bez grup (brak gatunki.json) — płaska lista", () => {
  const s = sel();
  buildSpeciesOptions(s, LIST.map(({ key, name }) => ({ key, name })), []);
  assert.deepEqual(s.children.map((o) => o.tag), ["option", "option", "option", "option", "option", "option"]);
  assert.deepEqual(s.children.map((o) => o.value), ["all", "borowik", "kurka", "kozlarz", "borowik_sosnowy", "kozlarz_czerwony"]);
});
