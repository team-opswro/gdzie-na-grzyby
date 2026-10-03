import { loadConfig, loadManifest, fileUrl, pogodaUrl, getJson } from "./config.js";

export const SPECIES = [
  { key: "borowik", name: "Borowik szlachetny" },
  { key: "podgrzybek", name: "Podgrzybek brunatny" },
  { key: "kurka", name: "Kurka" },
  { key: "kozlarz", name: "Koźlarz babka" },
  { key: "maslak", name: "Maślak zwyczajny" },
  { key: "rydz", name: "Rydz" },
];

export const ALL = "all";

const STALE_HOURS = 36;

export function weatherFor(pogoda, cell, species, dayIdx) {
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
  return {
    w: sp.w[dayIdx], rain: sp.rain[dayIdx], temp: sp.temp[dayIdx], season: sp.season[dayIdx],
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
export function bestFor(pogoda, cell, hBySpecies, dayIdx) {
  let best = null;
  for (const [species, h] of Object.entries(hBySpecies ?? {})) {
    if (h == null) continue;
    const wx = weatherFor(pogoda, cell, species, dayIdx);
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
