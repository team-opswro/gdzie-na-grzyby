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
  const wx = x ? { rain_mm: x.rain_mm?.[dayIdx], soil_t: x.soil_t?.[dayIdx], soil_m: x.soil_m?.[dayIdx] } : null;
  return {
    w: sp.w[dayIdx], rain: sp.rain[dayIdx], temp: sp.temp[dayIdx], season: sp.season[dayIdx],
    lim: sp.lim?.[dayIdx] ?? null,
    wx: wx && wx.rain_mm != null && wx.soil_t != null && wx.soil_m != null ? wx : null,
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

// Pogoda i centroidy ładują się niezależnie: awaria jednego nie wyrzuca drugiego.
export async function loadData(base = "data/") {
  const [c, p, n] = await Promise.allSettled([
    fetch(base + "centroidy.json").then((r) => {
      if (!r.ok) throw new Error(`centroidy.json: HTTP ${r.status}`);
      return r.json();
    }),
    fetch(base + "live/pogoda.json").then((r) => (r.ok ? r.json() : null)),
    fetch(base + "nazwy.json").then((r) => (r.ok ? r.json() : null)),
  ]);
  return {
    pogoda: p.status === "fulfilled" ? p.value : null,
    centroids: c.status === "fulfilled" ? c.value : null,
    nazwy: n.status === "fulfilled" ? n.value : null,
  };
}

// Lista gatunków z gatunki.json (limit czasu timeoutMs); przy błędzie lub zawieszeniu — wbudowane SPECIES (info: null).
export async function loadSpecies(base = "data/", timeoutMs = 3000) {
  const ctl = new AbortController();
  let timer;
  const timeout = new Promise((_, rej) => {
    timer = setTimeout(() => { ctl.abort(); rej(new Error("gatunki.json: timeout")); }, timeoutMs);
  });
  const load = async () => {
    const r = await fetch(base + "gatunki.json", { signal: ctl.signal });
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
