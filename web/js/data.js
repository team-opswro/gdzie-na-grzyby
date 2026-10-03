export const SPECIES = [
  { key: "borowik", name: "Borowik szlachetny" },
  { key: "podgrzybek", name: "Podgrzybek brunatny" },
  { key: "kurka", name: "Kurka" },
  { key: "kozlarz", name: "Koźlarz babka" },
  { key: "maslak", name: "Maślak zwyczajny" },
  { key: "rydz", name: "Rydz" },
];

const STALE_HOURS = 36;

export function weatherFor(pogoda, cell, species, dayIdx) {
  const sp = pogoda?.cells?.[cell]?.[species];
  if (!sp || sp.w?.[dayIdx] == null) return null;
  return { w: sp.w[dayIdx], rain: sp.rain[dayIdx], temp: sp.temp[dayIdx], season: sp.season[dayIdx] };
}

export function score(hInt, w) {
  return w == null ? null : Math.round(hInt * w);
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
  return now.getTime() - new Date(generatedAtIso).getTime() > STALE_HOURS * 3600 * 1000;
}

export function availableDays(days, todayIso) {
  return days.map((date, idx) => ({ date, idx })).filter((d) => d.date >= todayIso);
}

export async function loadData(base = "data/") {
  const [centroids, pogoda] = await Promise.all([
    fetch(base + "centroidy.json").then((r) => {
      if (!r.ok) throw new Error(`centroidy.json: HTTP ${r.status}`);
      return r.json();
    }),
    fetch(base + "live/pogoda.json")
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null),
  ]);
  return { pogoda, centroids };
}
