// Czyste funkcje service workera (klasyczny skrypt, importowany przez sw.js).
// Łatwe do testowania w Node przez vm.runInNewContext.
const SHELL_VERSION = 1;
const SHELL_CACHE = "grzyby-shell-" + SHELL_VERSION;
const DATA_CACHE = "grzyby-data";
const BASE_CACHE = "grzyby-base";
const LIMITS = { data: 3000, base: 2000 };
const NETWORK_TIMEOUT_MS = 4000;

const SHELL_FILES = [
  "index.html",
  "css/app.css",
  "js/config.js",
  "js/chart.js",
  "js/data.js",
  "js/dialogs.js",
  "js/hash.js",
  "js/map.js",
  "js/names.js",
  "js/popup.js",
  "js/ranking.js",
  "js/select.js",
  "js/share.js",
  "js/tiles.js",
  "js/ui.js",
  "vendor/maplibre-gl.css",
  "vendor/maplibre-gl.js",
  "vendor/pmtiles.js",
  "manifest.webmanifest",
  "icons/icon.svg",
];

function strategyFor(url, method, scope) {
  if (method !== "GET") return "pass";
  let u;
  try {
    u = new URL(url);
  } catch (e) {
    return "pass";
  }
  const pathname = u.pathname;
  const filename = pathname.substring(pathname.lastIndexOf("/") + 1);

  // Konfiguracja, manifest i prognoza — zawsze świeże, z fallbackiem do cache.
  if (filename === "config.json" || filename === "manifest.json" || pathname.endsWith("/live/pogoda.json")) {
    return "network-first";
  }

  // Niezmienne pliki wersjonowane (łącznie z lasy.pmtiles).
  if (/\/v\/[^/]+\//.test(pathname)) return "cache-first";

  // Podkłady — stale-while-revalidate (tylko już oglądane kafle).
  const host = u.hostname;
  if (host === "tile.openstreetmap.org" || host === "mapy.geoportal.gov.pl") return "swr";

  // Powłoka aplikacji.
  const rel = relativeToScope(url, scope);
  if (rel && SHELL_FILES.includes(rel)) return "cache-first";

  return "pass";
}

function relativeToScope(url, scope) {
  let scopeUrl;
  try {
    scopeUrl = new URL(scope);
  } catch (e) {
    return null;
  }
  let u;
  try {
    u = new URL(url);
  } catch (e) {
    return null;
  }
  if (u.origin !== scopeUrl.origin) return null;
  let rel = u.pathname.substring(scopeUrl.pathname.length);
  if (rel.startsWith("/")) rel = rel.substring(1);
  return rel;
}

function cacheKey(url, range) {
  return range ? url + "#range=" + range : url;
}

function trimPlan(keysOldestFirst, limit) {
  const excess = keysOldestFirst.length - limit;
  return excess > 0 ? keysOldestFirst.slice(0, excess) : [];
}

function staleShellCaches(names) {
  return names.filter((n) => n.startsWith("grzyby-shell-") && n !== SHELL_CACHE);
}

self.SWCore = {
  SHELL_VERSION,
  SHELL_CACHE,
  DATA_CACHE,
  BASE_CACHE,
  LIMITS,
  NETWORK_TIMEOUT_MS,
  SHELL_FILES,
  strategyFor,
  cacheKey,
  trimPlan,
  staleShellCaches,
};
