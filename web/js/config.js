// Skąd brać dane: config.json (generowany przy starcie kontenera z DATA_BASE_URL) → manifest.json → pliki wersji.
// Bez config.json lub bez DATA_BASE_URL — tryb lokalny "data/"; bez manifestu — pliki w katalogu głównym dataBase.

export const LOCAL_BASE = "data/";

export const LOCAL_MANIFEST = Object.freeze({
  build: null,
  base: "",
  generated_at: null,
  files: Object.freeze({
    lasy: "lasy.pmtiles",
    centroidy: "centroidy/index.json",
    grid: "grid.json",
    nazwy: "nazwy.json",
    gatunki: "gatunki.json",
  }),
});

export function normalizeBase(s) {
  if (typeof s !== "string") return LOCAL_BASE;
  const t = s.trim();
  if (!t) return LOCAL_BASE;
  return t.endsWith("/") ? t : t + "/";
}

async function getJson(fetcher, url) {
  const r = await fetcher(url, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}

export async function loadConfig(fetcher = globalThis.fetch) {
  try {
    const c = await getJson(fetcher, "config.json");
    return { dataBase: normalizeBase(c?.dataBase) };
  } catch {
    return { dataBase: LOCAL_BASE };
  }
}

// Brak (lub zły) manifest → LOCAL_MANIFEST: pliki leżą wprost w dataBase (układ pipeline/data/out).
export async function loadManifest(dataBase, fetcher = globalThis.fetch) {
  try {
    const m = await getJson(fetcher, dataBase + "manifest.json");
    if (m && typeof m.files === "object" && m.files !== null && typeof m.base === "string") return m;
    throw new Error("manifest.json: zły format");
  } catch (e) {
    if (!/^data\/?$/.test(dataBase)) console.warn("Brak manifest.json, pliki z katalogu głównego:", e?.message);
    return LOCAL_MANIFEST;
  }
}

export function fileUrl(dataBase, manifest, key) {
  const f = manifest?.files?.[key];
  return f ? dataBase + (manifest.base ?? "") + f : null;
}

// Prognoza jest poza wersją danych.
export function pogodaUrl(dataBase) {
  return dataBase + "live/pogoda.json";
}
