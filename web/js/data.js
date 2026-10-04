import { loadConfig, loadManifest, fileUrl, pogodaUrl, getJson } from "./config.js";

// Awaryjna lista (brak gatunki.json) — kolejność jak w species.yaml.
export const SPECIES = [
  { key: "borowik", name: "Borowik szlachetny", wet_gamma: 1.5 }, // wet_gamma jak w species.yaml (spec L)
  { key: "podgrzybek", name: "Podgrzybek brunatny" },
  { key: "kurka", name: "Kurka" },
  { key: "kozlarz", name: "Koźlarz babka" },
  { key: "maslak", name: "Maślak zwyczajny" },
  { key: "rydz", name: "Rydz mleczaj" },
  { key: "kozlarz_czerwony", name: "Koźlarz czerwony" },
  { key: "kozlarz_pomaranczowy", name: "Koźlarz pomarańczowożółty" },
  { key: "kozlarz_grabowy", name: "Koźlarz grabowy" },
  { key: "kozlarz_debowy", name: "Koźlarz dębowy" },
  { key: "borowik_sosnowy", name: "Borowik sosnowy" },
  { key: "borowik_usiatkowany", name: "Borowik usiatkowany" },
  { key: "podgrzybek_zajaczek", name: "Podgrzybek zajączek" },
  { key: "podgrzybek_zlotawy", name: "Podgrzybek złotawy" },
  { key: "podgrzybek_czerwonawy", name: "Podgrzybek czerwonawy" },
  { key: "maslak_zolty", name: "Maślak żółty" },
  { key: "maslak_sitarz", name: "Maślak sitarz" },
  { key: "rydz_swierkowy", name: "Rydz świerkowy" },
];

export const ALL = "all";
export const GROUP_PREFIX = "g-";

export function groupsOf(info) {
  return info?.groups ?? [];
}

// Wybór z listy (gatunek / "g-<grupa>" / "all") -> klucze gatunków; nieznane -> [].
export function selectionKeys(sel, speciesList, groups = []) {
  const keys = speciesList.map((s) => s.key);
  if (sel === ALL) return keys;
  if (typeof sel === "string" && sel.startsWith(GROUP_PREFIX)) {
    const g = groups.find((x) => GROUP_PREFIX + x.key === sel);
    return g ? g.species.filter((k) => keys.includes(k)) : [];
  }
  return keys.includes(sel) ? [sel] : [];
}

export function isMulti(sel) {
  return sel === ALL || (typeof sel === "string" && sel.startsWith(GROUP_PREFIX));
}

// Dozwolone wartości wyboru (dla parseHash).
export function selectionValues(speciesList, groups = []) {
  return [ALL, ...groups.map((g) => GROUP_PREFIX + g.key), ...speciesList.map((s) => s.key)];
}

const STALE_HOURS = 36;

// Wilgotność miejsca (spec L, wzór jak forecast/model.py: wet_adjust; przypadki: tests/fixtures/wet_cases.json):
// w_eff = min(1, w · rain^(γ−1)), γ = G^(1 − 2·wet/100), G = wet_gamma gatunku z gatunki.json (domyślnie 3).
// Brak wet/rain lub rain ≤ 0 → w bez zmian.
export const WET_GAMMA_BASE = 3;
const wetGammas = new Map();

// Lista gatunków z gatunki.json ([{key, wet_gamma?}]); brak pola → WET_GAMMA_BASE.
export function setWetGammas(list) {
  wetGammas.clear();
  for (const s of list ?? []) if (Number.isFinite(s?.wet_gamma)) wetGammas.set(s.key, s.wet_gamma);
}

export function wetGammaFor(species) {
  return wetGammas.get(species) ?? WET_GAMMA_BASE;
}

export function toWet(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function adjustW(w, rain, wet, base = WET_GAMMA_BASE) {
  const x = toWet(wet);
  if (w == null || rain == null || x == null || !(rain > 0)) return w;
  const gamma = base ** (1 - (2 * x) / 100);
  return Math.min(1, w * rain ** (gamma - 1));
}

// wet (atrybut wydzielenia, opcjonalny): w zwracane jest skorygowane, w_raw — z pogoda.json.
export function weatherFor(pogoda, cell, species, dayIdx, wet = null) {
  const sp = pogoda?.cells?.[cell]?.[species];
  if (!sp || sp.w?.[dayIdx] == null) return null;
  const x = pogoda.wx?.[cell];
  const wx = x ? {
    rain_mm: x.rain_mm?.[dayIdx],
    soil_t: x.soil_t?.[dayIdx],
    soil_m: x.soil_m?.[dayIdx],
    ...(x.et0_mm && { et0_mm: x.et0_mm[dayIdx] }),
    ...(x.soil_m_deep && { soil_m_deep: x.soil_m_deep[dayIdx] }),
    ...(x.t2m_min && { t2m_min: x.t2m_min[dayIdx] }),
  } : null;
  const hasBaseWx = wx && wx.rain_mm != null && wx.soil_t != null && wx.soil_m != null;
  const w = sp.w[dayIdx];
  const rain = sp.rain?.[dayIdx] ?? null;
  const wetN = toWet(wet);
  return {
    w: wetN == null ? w : adjustW(w, rain, wetN, wetGammaFor(species)),
    ...(wetN != null && { w_raw: w, wet: wetN }),
    rain, temp: sp.temp[dayIdx], season: sp.season[dayIdx],
    pulse: sp.pulse?.[dayIdx] ?? null,
    frost: sp.frost?.[dayIdx] ?? null,
    lim: sp.lim?.[dayIdx] ?? null,
    wx: hasBaseWx ? wx : null,
  };
}

export function score(hInt, w) {
  return w == null ? null : Math.round(hInt * w);
}

// Najlepszy gatunek w komórce: max round(h_k * w_k); gatunki bez pogody lub bez h są pomijane.
// wet: wilgotność miejsca wydzielenia (spec L), opcjonalna.
export function bestFor(pogoda, cell, hBySpecies, dayIdx, wet = null) {
  let best = null;
  for (const [species, h] of Object.entries(hBySpecies ?? {})) {
    if (h == null) continue;
    const wx = weatherFor(pogoda, cell, species, dayIdx, wet);
    if (!wx) continue;
    const s = score(h, wx.w);
    if (best == null || s > best.score) best = { species, score: s, wx };
  }
  return best;
}

export function scoreClass(s) {
  if (s == null) return null;
  if (s < 10) return 0;
  if (s < 25) return 1;
  if (s < 45) return 2;
  if (s <= 65) return 3;
  return 4;
}

export function isStale(generatedAtIso, now = new Date()) {
  const age = now.getTime() - new Date(generatedAtIso).getTime();
  return Number.isNaN(age) || age > STALE_HOURS * 3600 * 1000;
}

export function availableDays(days, todayIso) {
  return days.map((date, idx) => ({ date, idx })).filter((d) => d.date >= todayIso);
}

// Tekst banera nad mapą (null = wszystko w porządku).
export function bannerText(pogoda, availableDaysCount, now = new Date()) {
  const habitatOnly = "mapa pokazuje tylko ocenę siedliska";
  if (!pogoda) return `Brak danych pogodowych — ${habitatOnly}`;
  if (isStale(pogoda.generated_at, now)) {
    const text = `Prognoza nieaktualna (z dnia ${String(pogoda.generated_at).slice(0, 10)})`;
    return availableDaysCount > 0 ? text : `${text}, ${habitatOnly}`;
  }
  return availableDaysCount > 0 ? null : `Brak aktualnych dni w prognozie — ${habitatOnly}`;
}

// config.json → manifest.json → pliki wersji; pogoda z live/. Każdy plik ładuje się niezależnie:
// awaria jednego nie wyrzuca pozostałych. Centroidy: tylko indeks kafelków (kafelki — tiles.js).
export const DATA_TIMEOUT_MS = 30000; // słaby zasięg w lesie; pogoda.json ~150 kB (gzip)

export async function loadData({ dataBase, manifest, timeoutMs = DATA_TIMEOUT_MS } = {}) {
  dataBase ??= (await loadConfig()).dataBase;
  manifest ??= await loadManifest(dataBase);
  const json = (url, cache = "default") =>
    url ? getJson(globalThis.fetch, url, timeoutMs, cache) : Promise.reject(new Error("brak pliku w manifeście"));
  const [c, p, n] = await Promise.allSettled([
    json(fileUrl(dataBase, manifest, "centroidy")),
    json(pogodaUrl(dataBase), "no-cache"),
    json(fileUrl(dataBase, manifest, "nazwy")),
  ]);
  const val = (x) => (x.status === "fulfilled" ? x.value : null);
  return { pogoda: val(p), centroidIndex: val(c), nazwy: val(n), manifest, dataBase };
}

// Lista gatunków z gatunki.json (limit czasu timeoutMs); przy błędzie lub zawieszeniu — wbudowane SPECIES (info: null).
export async function loadSpecies(url = "data/gatunki.json", timeoutMs = 3000) {
  const ctl = new AbortController();
  let timer;
  const timeout = new Promise((_, rej) => {
    timer = setTimeout(() => { ctl.abort(); rej(new Error("gatunki.json: timeout")); }, timeoutMs);
  });
  const load = async () => {
    if (!url) throw new Error("gatunki.json: brak w manifeście");
    const r = await fetch(url, { signal: ctl.signal });
    if (!r.ok) throw new Error(`gatunki.json: HTTP ${r.status}`);
    const info = await r.json();
    if (!Array.isArray(info?.species) || info.species.length === 0) throw new Error("gatunki.json: brak listy");
    return { list: info.species, info };
  };
  try {
    return await Promise.race([load(), timeout]);
  } catch {
    return { list: SPECIES, info: null };
  } finally {
    clearTimeout(timer);
  }
}
