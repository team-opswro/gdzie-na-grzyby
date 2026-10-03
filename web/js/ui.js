import { SPECIES, bestFor, loadData, loadSpecies, availableDays, bannerText, groupsOf, selectionValues, selectionKeys, isMulti } from "./data.js";
import { buildSpeciesOptions } from "./select.js";
import { loadConfig, loadManifest, fileUrl } from "./config.js";
import { createCentroidStore } from "./tiles.js";
import { trend, trendBy } from "./chart.js";
import { topN, haversineKm } from "./ranking.js";
import { parseHash, formatHash } from "./hash.js";
import { createMap, addForestLayers, setView, setBasemap, BASEMAPS, COLORS, CLASS_LABELS, FILL_OPACITY } from "./map.js";
import { renderPopup, renderReserve, renderParking, trendArrow, trendLabel, rankLabel } from "./popup.js";
import { shareUrl } from "./share.js";
import { speciesCardModel, renderSpeciesCard, aboutForecastText } from "./dialogs.js";

const OPOLSKIE_CENTER = [17.9, 50.65];
const DEFAULT_ZOOM = 9;
const $ = (id) => document.getElementById(id);

// Lokalna data ISO (toISOString dałby UTC).
export function todayLocalIso(now = new Date()) {
  const p = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`;
}

function formatDay(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("pl-PL", { weekday: "short", day: "numeric", month: "short" });
}

const MAP_DATA_ERROR = "Nie udało się wczytać danych mapy";

export async function init() {
  // Rejestracja service workera (PWA) — tylko przez HTTP(S), nie z file://.
  if ("serviceWorker" in navigator && location.protocol !== "file:") {
    navigator.serviceWorker.register("sw.js").catch((e) => console.warn("SW:", e));
  }

  // Podkład powstaje od razu (zawieszony bucket ≠ pusta strona); warstwy lasów dochodzą po manifeście.
  // Wstępny hash: środek, zoom i podkład nie zależą od listy gatunków.
  const pre = parseHash(location.hash, selectionValues(SPECIES));
  const handlers = {}; // uzupełniane niżej, gdy stan jest gotowy
  const map = createMap($("map"), {
    center: pre.center ?? OPOLSKIE_CENTER,
    zoom: pre.zoom ?? DEFAULT_ZOOM,
    basemap: pre.basemap,
    onFeatureClick: (props, lngLat) => handlers.feature?.(props, lngLat),
    onReserveClick: (name, lngLat) => handlers.reserve?.(name, lngLat),
    onParkingClick: (props, lngLat) => handlers.parking?.(props, lngLat),
    onMove: () => handlers.move?.(),
  });
  const styleLoaded = new Promise((resolve) => map.once("load", resolve));

  const { dataBase } = await loadConfig();
  const manifest = await loadManifest(dataBase);
  const pmtilesUrl = fileUrl(dataBase, manifest, "lasy");
  const mapDataError = manifest.missing || !pmtilesUrl;
  if (mapDataError) showBanner();
  const { list: speciesList, info: speciesInfo } = await loadSpecies(fileUrl(dataBase, manifest, "gatunki"));
  const groups = groupsOf(speciesInfo);
  const hash = parseHash(location.hash, selectionValues(speciesList, groups));
  const state = { species: hash.species, day: hash.day, basemap: hash.basemap, radius: hash.radius, place: hash.place };
  // Gatunki bieżącego wyboru: jeden klucz, grupa albo wszystkie (tryb wielu gatunków, gdy > 1).
  const keys = () => selectionKeys(state.species, speciesList, groups);
  let data = { pogoda: null, centroidIndex: null, nazwy: null };
  let nazwy = null;
  let todayIso = todayLocalIso(); // stała data dnia, wspólna dla days i popupu
  let days = []; // availableDays(...) — pozycja w tej tablicy to „day” w hashu
  let gps = null; // {lat, lon} po zgodzie na lokalizację
  let popup = null;
  let lastPopup = null; // {props, lngLat} ostatnio otwartego wydzielenia
  let mapReady = false;
  let loaded = false;
  let placeTried = false; // jednorazowe otwarcie popupu z parametru w=

  const sel = $("species");
  buildSpeciesOptions(sel, speciesList, groups);
  sel.value = state.species;
  buildLegend();
  const infoBtn = $("species-info");
  const syncInfoBtn = () => { infoBtn.disabled = isMulti(state.species); };
  syncInfoBtn();
  infoBtn.addEventListener("click", () => {
    $("species-card-body").replaceChildren(renderSpeciesCard(speciesCardModel(speciesInfo, state.species)));
    openDialog($("species-card"), infoBtn);
  });
  document.querySelectorAll(".about-link").forEach((a) => a.addEventListener("click", (e) => {
    e.preventDefault();
    $("about-forecast").textContent = aboutForecastText(data.pogoda?.generated_at);
    openDialog($("about"), a);
  }));
  document.querySelectorAll("dialog").forEach((d) => {
    d.querySelector(".dlg-close").addEventListener("click", () => d.close());
    d.addEventListener("close", () => d._opener?.focus?.());
  });
  updateAttribution(state.basemap);

  // Mapa powstaje od razu (styl samego h); pogoda i centroidy dołączają po załadowaniu.
  let pogoda = null;
  let centroids = null; // createCentroidStore(...) po wczytaniu indeksu kafelków
  let effective = null;
  const dayIdx = () => (days.length ? days[state.day].idx : 0);

  handlers.feature = (props, lngLat) => showPopup(props, lngLat);
  handlers.parking = (props, lngLat) => {
    popup?.remove();
    lastPopup = null;
    const content = renderParking(props, lngLat);
    const pp = new maplibregl.Popup({ maxWidth: "280px" }).setLngLat(lngLat).setDOMContent(content).addTo(map);
    popup = pp;
    pp.on("close", () => { if (popup === pp) popup = null; });
  };
  handlers.reserve = (name, lngLat) => {
    popup?.remove();
    lastPopup = null;
    const content = document.createElement("div");
    content.className = "popup";
    content.append(renderReserve(name));
    popup = new maplibregl.Popup({ maxWidth: "280px" }).setLngLat(lngLat).setDOMContent(content).addTo(map);
  };
  handlers.move = () => {
    writeHash();
    if (!gps) updateRanking();
  };
  styleLoaded.then(() => {
    if (pmtilesUrl) {
      addForestLayers(map, pmtilesUrl, { pogoda: effective, species: keys(), dayIdx: dayIdx(), basemap: state.basemap });
    }
    mapReady = true;
    setBasemap(map, state.basemap); // przełączenie podkładu kliknięte przed końcem ładowania stylu
    setView(map, effective, keys(), dayIdx());
    if (loaded) map.once("idle", openInitialPlace);
  });
  map.on("idle", openInitialPlace);

  // Jednorazowe otwarcie wydzielenia z parametru w= po załadowaniu danych.
  // Centroid szukany w kafelku środka z hasha i 8 sąsiednich.
  async function openInitialPlace() {
    if (placeTried || !loaded || !mapReady || !state.place || !map.getLayer("lasy-fill")) return;
    placeTried = true;
    const byId = (x) => x.properties.id === state.place;
    const [hLon, hLat] = hash.center ?? [map.getCenter().lng, map.getCenter().lat];
    const row = centroids ? await centroids.findRow(state.place, hLat, hLon).catch(() => null) : null;
    const open = (lngLat) => {
      const f = (lngLat ? map.queryRenderedFeatures(map.project([lngLat.lng, lngLat.lat]), { layers: ["lasy-fill"] }).find(byId) : null)
        ?? map.queryRenderedFeatures({ layers: ["lasy-fill"] }).find(byId);
      if (f) showPopup(f.properties, lngLat ?? map.getCenter(), { pan: false });
      else writeHash(); // martwe w= znika z hasha
    };
    if (!row) {
      const c = map.getCenter();
      open({ lng: c.lng, lat: c.lat });
      return;
    }
    const lngLat = { lng: row[2], lat: row[1] };
    if (map.getBounds().contains([lngLat.lng, lngLat.lat])) open(lngLat);
    else {
      map.once("idle", () => open(lngLat));
      map.jumpTo({ center: [lngLat.lng, lngLat.lat] });
    }
  }

  function showPopup(props, lngLat, { pan = true } = {}) {
    popup?.remove();
    lastPopup = { props, lngLat };
    const content = renderPopup(props, {
      pogoda: effective,
      species: state.species,
      keys: keys(),
      speciesList,
      dayIdx: dayIdx(),
      todayIso,
      onDaySelect,
      nazwy,
      lngLat,
      onShare: sharePlace,
    });
    const pp = new maplibregl.Popup({ maxWidth: "280px" }).setLngLat(lngLat).setDOMContent(content).addTo(map);
    popup = pp;
    pp.on("close", () => {
      if (popup === pp) {
        popup = null;
        lastPopup = null;
        writeHash(); // zamknięcie popupu usuwa w z hasha
      }
    });
    // Na telefonie popup ma się w całości zmieścić nad zwiniętym panelem (zakotwiczony pod punktem).
    if (pan && window.matchMedia("(max-width: 700px)").matches) {
      const mapEl = map.getContainer();
      const panelTop = $("panel").getBoundingClientRect().top - mapEl.getBoundingClientRect().top;
      const pr = pp.getElement().getBoundingClientRect();
      const mapTop = mapEl.getBoundingClientRect().top;
      if (pr.bottom - mapTop > panelTop - 6) {
        const tipTarget = Math.max(12, panelTop - 6 - pr.height - 4);
        map.easeTo({ center: [lngLat.lng, lngLat.lat], offset: [0, tipTarget - mapEl.clientHeight / 2], duration: 300 });
      }
    }
    writeHash();
    return content;
  }

  function sharePlace(props, lngLat) {
    const url = location.href.split("#")[0] + formatHash({
      species: state.species,
      day: state.day,
      zoom: Math.max(map.getZoom(), 15),
      center: [lngLat.lng, lngLat.lat],
      basemap: state.basemap,
      radius: state.radius,
      place: props.id,
    });
    return shareUrl(url, document.title, { notify: toast });
  }

  let toastTimer = 0;
  function toast(text) {
    const t = $("toast");
    clearTimeout(toastTimer);
    t.classList.add("show");
    t.textContent = "";
    setTimeout(() => { t.textContent = text; }, 50);
    toastTimer = setTimeout(() => { t.classList.remove("show"); t.textContent = ""; }, 2000);
  }

  function onDaySelect(idx) {
    const p = days.findIndex((d) => d.idx === idx);
    if (p < 0) return;
    const keep = lastPopup;
    state.day = p;
    refresh();
    if (keep) {
      const content = showPopup(keep.props, keep.lngLat, { pan: false });
      content.querySelector('[aria-pressed="true"]')?.focus?.();
    }
  }

  function writeHash() {
    const c = map.getCenter();
    const coarse = !!gps && haversineKm(gps, { lat: c.lat, lon: c.lng }) < 0.2;
    history.replaceState(null, "", formatHash({
      species: state.species,
      day: state.day,
      zoom: map.getZoom(),
      center: [c.lng, c.lat],
      coarse,
      basemap: state.basemap,
      radius: state.radius,
      place: lastPopup?.props.id,
    }));
  }

  function origin() {
    if (gps) return gps;
    const c = map.getCenter();
    return { lat: c.lat, lon: c.lng };
  }

  let rankingSeq = 0; // tylko najnowsze wywołanie (kafelki ładują się asynchronicznie) rysuje listę
  async function updateRanking() {
    const seq = ++rankingSeq;
    const list = $("ranking-list");
    const show = (...items) => { if (seq === rankingSeq) list.replaceChildren(...items); };
    if (!loaded) return show();
    if (!centroids) return show(li("Nie udało się wczytać danych rankingu.", "empty"));
    if (!effective) return show(li("Brak danych pogodowych", "empty"));
    const o = origin();
    const radius = state.radius;
    let top;
    try {
      const rows = await centroids.rowsNear(o, radius);
      if (seq !== rankingSeq) return;
      top = topN({ species: centroids.species, rows }, effective, keys(), dayIdx(), o, radius);
    } catch (e) {
      console.warn("Ranking:", e);
      return show(li("Nie udało się wczytać danych rankingu.", "empty"));
    }
    list.replaceChildren();
    if (!top.length) {
      list.append(li(`Brak miejsc o dodatnim wyniku w promieniu ${radius} km`, "empty"));
      return;
    }
    top.forEach((r, i) => {
      const item = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      const sc = document.createElement("span");
      sc.className = "rank-score";
      sc.textContent = r.best.score;
      const tr = document.createElement("span");
      tr.className = "rank-trend";
      const t = r.best.hBy
        ? trendBy(effective, (i) => (i < 0 ? null : bestFor(effective, r.best.cell, r.best.hBy, i)?.score ?? null), dayIdx())
        : trend(effective, r.best.cell, keys()[0], r.best.h, dayIdx());
      if (t.dir) {
        tr.textContent = trendArrow(t.dir);
        tr.title = `${t.delta > 0 ? "+" : ""}${t.delta} względem poprzedniego dnia`;
        const sr = document.createElement("span");
        sr.className = "sr-only";
        sr.textContent = trendLabel(t);
        tr.append(sr);
      }
      const { line1, line2 } = rankLabel(r, nazwy, speciesList);
      const text = document.createElement("span");
      text.className = "rank-text";
      const name = document.createElement("span");
      name.className = "rank-name";
      name.textContent = line1;
      const dist = document.createElement("span");
      dist.className = "rank-dist";
      dist.textContent = line2;
      text.append(name, dist);
      btn.append(sc, tr, text);
      btn.addEventListener("click", () => flyToRow(r.best));
      item.append(btn);
      list.append(item);
    });
  }

  function li(text, cls) {
    const e = document.createElement("li");
    e.className = cls;
    e.textContent = text;
    return e;
  }

  function flyToRow(r) {
    if (window.matchMedia("(max-width: 700px)").matches) setPanelOpen(false);
    map.once("idle", () => {
      if (!map.getLayer("lasy-fill")) return;
      const f = map.queryRenderedFeatures(map.project([r.lon, r.lat]), { layers: ["lasy-fill"] }).find((x) => x.properties.id === r.id);
      if (f) showPopup(f.properties, { lng: r.lon, lat: r.lat });
    });
    map.flyTo({ center: [r.lon, r.lat], zoom: Math.max(map.getZoom(), 14) });
  }

  function refresh() {
    if (mapReady) setView(map, effective, keys(), dayIdx());
    updateDayControls();
    updateRanking();
    writeHash();
    popup?.remove();
  }

  function updateDayControls() {
    const label = $("day-label");
    const none = !days.length;
    label.textContent = none ? "—" : formatDay(days[state.day].date);
    $("day-prev").disabled = none || state.day <= 0;
    $("day-next").disabled = none || state.day >= days.length - 1;
  }

  sel.addEventListener("change", () => { state.species = sel.value; syncInfoBtn(); refresh(); });
  $("day-prev").addEventListener("click", () => { state.day--; refresh(); });
  $("day-next").addEventListener("click", () => { state.day++; refresh(); });

  function updateSource(gpsError = false) {
    $("ranking-source").textContent = gps
      ? "od Twojej lokalizacji"
      : gpsError
        ? "Brak zgody na lokalizację — ranking od środka mapy"
        : "od środka mapy";
  }

  let locating = false;
  $("locate").addEventListener("click", () => {
    if (gps) {
      gps = null;
      $("locate").setAttribute("aria-pressed", "false");
      updateSource();
      updateRanking();
      return;
    }
    if (locating) return;
    if (!navigator.geolocation) { updateSource(true); return; }
    locating = true;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        locating = false;
        gps = { lat: pos.coords.latitude, lon: pos.coords.longitude };
        $("locate").setAttribute("aria-pressed", "true");
        updateSource();
        map.flyTo({ center: [gps.lon, gps.lat], zoom: Math.max(map.getZoom(), 12) });
        updateRanking();
      },
      () => {
        locating = false;
        gps = null;
        $("locate").setAttribute("aria-pressed", "false");
        updateSource(true);
        updateRanking();
      },
      { enableHighAccuracy: false, timeout: 10000 },
    );
  });

  $("share").addEventListener("click", () => shareUrl(location.href, document.title, { notify: toast }));

  const radiusSel = $("radius");
  radiusSel.value = String(state.radius);
  radiusSel.addEventListener("change", () => {
    state.radius = Number(radiusSel.value);
    updateRanking();
    writeHash();
  });

  buildSwitcher(state.basemap, (key) => {
    state.basemap = key;
    if (mapReady) setBasemap(map, key);
    updateAttribution(key);
    writeHash();
  });

  function setPanelOpen(open) {
    $("panel").classList.toggle("open", open);
    $("panel-toggle").setAttribute("aria-expanded", String(open));
  }
  $("panel-toggle").addEventListener("click", () => setPanelOpen(!$("panel").classList.contains("open")));

  updateDayControls();
  data = await loadData({ dataBase, manifest });
  ({ pogoda, nazwy } = data);
  const tilesIdx = fileUrl(dataBase, manifest, "centroidy");
  if (data.centroidIndex && tilesIdx) {
    centroids = createCentroidStore((u, init) => fetch(u, init), tilesIdx.slice(0, tilesIdx.lastIndexOf("/") + 1), data.centroidIndex);
  }
  todayIso = todayLocalIso();
  if (pogoda) days = availableDays(pogoda.days, todayIso);
  state.day = Math.min(state.day, Math.max(days.length - 1, 0));
  // Bez dostępnych dni mapa koloruje samym h (jak przy braku pliku).
  effective = days.length ? pogoda : null;
  loaded = true;
  showBanner(bannerText(pogoda, days.length));
  if (mapReady) setView(map, effective, keys(), dayIdx());
  updateDayControls();
  updateRanking();
  if (mapReady) map.once("idle", openInitialPlace);
  return map;

  // Baner nad mapą: błąd danych mapy (manifest) + stan prognozy + tryb offline.
  function showBanner(weather = null) {
    const parts = [mapDataError ? MAP_DATA_ERROR : null, weather].filter(Boolean);
    if (navigator.onLine === false && data.pogoda?.generated_at) {
      const when = aboutForecastText(data.pogoda.generated_at).replace("Prognoza z: ", "");
      parts.push(`Tryb offline — dane z ${when}`);
    }
    const text = parts.join(". ");
    $("stale").textContent = text;
    $("stale").hidden = !text;
  }
}

function openDialog(dlg, opener) {
  dlg._opener = opener;
  if (typeof dlg.showModal === "function") dlg.showModal();
  else dlg.setAttribute("open", "");
  // showModal fokusuje pierwszy element interaktywny (na dole) — startujemy od nagłówka.
  const h = dlg.querySelector("h2");
  if (h) {
    h.tabIndex = -1;
    h.focus({ preventScroll: true });
  }
  dlg.scrollTop = 0;
}

function buildLegend() {
  const box = $("legend");
  const add = (color, text, opacity, cls) => {
    const s = document.createElement("span");
    const sw = document.createElement("i");
    if (cls) sw.className = cls;
    else sw.style.background = color;
    if (opacity) sw.style.opacity = String(opacity);
    s.append(sw, text);
    box.append(s);
  };
  COLORS.classes.forEach((c, i) => add(c, CLASS_LABELS[i], i === 0 ? FILL_OPACITY.weak : FILL_OPACITY.normal));
  add(COLORS.noData, "brak danych", FILL_OPACITY.noData);
  add("#757575", "rezerwat — zbiór zabroniony", null, "hatch");
  const link = document.createElement("a");
  link.href = "#";
  link.className = "about-link";
  link.textContent = "Jak to działa?";
  const s = document.createElement("span");
  s.append(link);
  box.append(s);
}

const BASEMAP_LABELS = [["osm", "Mapa"], ["orto", "Satelita"], ["topo", "Topo"]];

function updateAttribution(key) {
  const box = $("attr-base");
  if (!box) return;
  box.replaceChildren();
  if (key === "osm") {
    const a = document.createElement("a");
    a.href = "https://www.openstreetmap.org/copyright";
    a.textContent = "OpenStreetMap";
    box.append("© ", a);
  } else {
    box.append(BASEMAPS[key].attribution);
  }
}

function buildSwitcher(current, onChange) {
  const box = $("basemap");
  const buttons = BASEMAP_LABELS.map(([key, label]) => {
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("role", "radio");
    b.dataset.key = key;
    b.textContent = label;
    b.addEventListener("click", () => { onChange(key); select(key); });
    return b;
  });
  const select = (key) => buttons.forEach((b) => b.setAttribute("aria-checked", String(b.dataset.key === key)));
  box.append(...buttons);
  select(current);
}
