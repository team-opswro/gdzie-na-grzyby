import { ALL, GROUP_PREFIX } from "./data.js";

function option(value, text) {
  const o = document.createElement("option");
  o.value = value;
  o.textContent = text;
  return o;
}

// Lista wyboru: „Wszystkie gatunki”, potem optgroup na grupę (pierwsza opcja = cała grupa),
// na końcu „Inne” (gatunki bez grupy). Bez grup (brak gatunki.json) — płaska lista.
export function buildSpeciesOptions(selectEl, speciesList, groups = []) {
  selectEl.append(option(ALL, "Wszystkie gatunki"));
  if (!groups.length) {
    for (const s of speciesList) selectEl.append(option(s.key, s.name));
    return;
  }
  const byKey = new Map(speciesList.map((s) => [s.key, s]));
  const grouped = new Set();
  for (const g of groups) {
    const og = document.createElement("optgroup");
    og.label = g.name;
    og.append(option(GROUP_PREFIX + g.key, g.all));
    for (const k of g.species) {
      const s = byKey.get(k);
      if (!s) continue;
      og.append(option(s.key, s.name));
      grouped.add(k);
    }
    selectEl.append(og);
  }
  const rest = speciesList.filter((s) => !grouped.has(s.key));
  if (rest.length) {
    const og = document.createElement("optgroup");
    og.label = "Inne";
    for (const s of rest) og.append(option(s.key, s.name));
    selectEl.append(og);
  }
}
