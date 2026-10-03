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

export const FETCH_TIMEOUT_MS = 4000;

// fetch JSON z limitem czasu: zawieszony serwer (bucket) nie może zablokować strony.
// cache: "no-cache" (domyślnie) dla plików zmiennych; pliki wersji (immutable) — "default".
export async function getJson(fetcher, url, timeoutMs = FETCH_TIMEOUT_MS, cache = "no-cache") {
  const ctl = new AbortController();
  let timer;
  const timeout = new Promise((_, rej) => {
    timer = setTimeout(() => { ctl.abort(); rej(new Error(`${url}: timeout`)); }, timeoutMs);
  });
  const load = async () => {
    const r = await fetcher(url, { cache, signal: ctl.signal });
    if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    return r.json();
  };
  try {
    return await Promise.race([load(), timeout]);
  } finally {
    clearTimeout(timer);
  }
}

export async function loadConfig(fetcher = globalThis.fetch, timeoutMs = FETCH_TIMEOUT_MS) {
  try {
    const c = await getJson(fetcher, "config.json", timeoutMs);
    return { dataBase: normalizeBase(c?.dataBase) };
  } catch {
    return { dataBase: LOCAL_BASE };
  }
}

export const isLocalBase = (dataBase) => dataBase === LOCAL_BASE;

// Brak (lub zły / zawieszony) manifest:
// - dataBase "data/" → LOCAL_MANIFEST: pliki wprost w data/ (układ pipeline/data/out),
// - inny dataBase → manifest bez plików z missing: true (UI pokazuje baner; prognoza z live/ nadal działa).
export async function loadManifest(dataBase, fetcher = globalThis.fetch, timeoutMs = FETCH_TIMEOUT_MS) {
  try {
    const m = await getJson(fetcher, dataBase + "manifest.json", timeoutMs);
    if (m && typeof m.files === "object" && m.files !== null && typeof m.base === "string") return m;
    throw new Error("manifest.json: zły format");
  } catch (e) {
    if (isLocalBase(dataBase)) return LOCAL_MANIFEST;
    console.warn("Nie udało się wczytać manifest.json:", e?.message);
    return { build: null, base: "", generated_at: null, files: {}, missing: true };
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
