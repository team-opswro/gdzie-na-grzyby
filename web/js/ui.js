import { SPECIES, loadData, availableDays, bannerText } from "./data.js";
import { trend } from "./chart.js";
import { topN } from "./ranking.js";
import { parseHash, formatHash } from "./hash.js";
import { createMap, setView, setBasemap, BASEMAPS, COLORS, CLASS_LABELS, FILL_OPACITY } from "./map.js";
import { renderPopup, renderReserve, trendArrow, trendLabel, rankLabel } from "./popup.js";
import { shareUrl } from "./share.js";

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

export async function init() {
  const hash = parseHash(location.hash);
  const state = { species: hash.species, day: hash.day, basemap: hash.basemap, radius: hash.radius, place: hash.place };
  let data = { pogoda: null, centroids: null, nazwy: null };
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
  for (const s of SPECIES) sel.append(new Option(s.name, s.key));
  sel.value = state.species;
  buildLegend();
  updateAttribution(state.basemap);

  // Mapa powstaje od razu (styl samego h); pogoda i centroidy dołączają po załadowaniu.
  let pogoda = null;
  let centroids = null;
  let effective = null;
  const dayIdx = () => (days.length ? days[state.day].idx : 0);

  const map = createMap($("map"), {
    center: hash.center ?? OPOLSKIE_CENTER,
    zoom: hash.zoom ?? DEFAULT_ZOOM,
    pogoda: null,
    species: state.species,
    dayIdx: 0,
    basemap: state.basemap,
    onFeatureClick: (props, lngLat) => showPopup(props, lngLat),
    onReserveClick: (name, lngLat) => {
      popup?.remove();
      lastPopup = null;
      const content = document.createElement("div");
      content.className = "popup";
      content.append(renderReserve(name));
      popup = new maplibregl.Popup({ maxWidth: "280px" }).setLngLat(lngLat).setDOMContent(content).addTo(map);
    },
    onMove: () => {
      writeHash();
      if (!gps) updateRanking();
    },
  });
  map.on("load", () => {
    mapReady = true;
    setBasemap(map, state.basemap); // przełączenie podkładu kliknięte przed końcem ładowania stylu
    setView(map, effective, state.species, dayIdx());
  });
  map.on("idle", openInitialPlace);

  // Jednorazowe otwarcie wydzielenia z parametru w= po załadowaniu danych.
  function openInitialPlace() {
    if (placeTried || !loaded || !mapReady || !state.place) return;
    placeTried = true;
    const c = map.getCenter();
    const byId = (x) => x.properties.id === state.place;
    const f = map.queryRenderedFeatures(map.project(c), { layers: ["lasy-fill"] }).find(byId)
      ?? map.queryRenderedFeatures({ layers: ["lasy-fill"] }).find(byId);
    if (f) showPopup(f.properties, { lng: c.lng, lat: c.lat }, { pan: false });
  }

  function showPopup(props, lngLat, { pan = true } = {}) {
    popup?.remove();
    lastPopup = { props, lngLat };
    const content = renderPopup(props, {
      pogoda: effective,
      species: state.species,
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
    // Na telefonie popup ma być w górnej części ekranu, nad zwiniętym panelem.
    if (pan && window.matchMedia("(max-width: 700px)").matches
      && map.project([lngLat.lng, lngLat.lat]).y > map.getContainer().clientHeight / 3) {
      map.easeTo({ center: [lngLat.lng, lngLat.lat], offset: [0, -map.getContainer().clientHeight / 6], duration: 300 });
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
    history.replaceState(null, "", url);
    return shareUrl(location.href, document.title, { notify: toast });
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
    history.replaceState(null, "", formatHash({
      species: state.species,
      day: state.day,
      zoom: map.getZoom(),
      center: [c.lng, c.lat],
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

  function updateRanking() {
    const list = $("ranking-list");
    list.replaceChildren();
    if (!loaded) return;
    if (!centroids) {
      list.append(li("Nie udało się wczytać danych rankingu.", "empty"));
      return;
    }
    if (!effective) {
      list.append(li("Brak danych pogodowych", "empty"));
      return;
    }
    const top = topN(centroids, effective, state.species, dayIdx(), origin(), state.radius);
    if (!top.length) {
      list.append(li(`Brak miejsc o dodatnim wyniku w promieniu ${state.radius} km`, "empty"));
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
      const t = trend(effective, r.best.cell, state.species, r.best.h, dayIdx());
      if (t.dir) {
        tr.textContent = trendArrow(t.dir);
        tr.title = `${t.delta > 0 ? "+" : ""}${t.delta} względem poprzedniego dnia`;
        tr.setAttribute("aria-label", trendLabel(t));
      }
      const { line1, line2 } = rankLabel(r, nazwy);
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
      const f = map.queryRenderedFeatures(map.project([r.lon, r.lat]), { layers: ["lasy-fill"] }).find((x) => x.properties.id === r.id);
      if (f) showPopup(f.properties, { lng: r.lon, lat: r.lat });
    });
    map.flyTo({ center: [r.lon, r.lat], zoom: Math.max(map.getZoom(), 14) });
  }

  function refresh() {
    if (mapReady) setView(map, effective, state.species, dayIdx());
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

  sel.addEventListener("change", () => { state.species = sel.value; refresh(); });
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
  data = await loadData();
  ({ pogoda, centroids, nazwy } = data);
  todayIso = todayLocalIso();
  if (pogoda) days = availableDays(pogoda.days, todayIso);
  state.day = Math.min(state.day, Math.max(days.length - 1, 0));
  // Bez dostępnych dni mapa koloruje samym h (jak przy braku pliku).
  effective = days.length ? pogoda : null;
  loaded = true;
  const banner = bannerText(pogoda, days.length);
  if (banner) {
    $("stale").textContent = banner;
    $("stale").hidden = false;
  }
  if (mapReady) setView(map, effective, state.species, dayIdx());
  updateDayControls();
  updateRanking();
  if (mapReady) map.once("idle", openInitialPlace);
  return map;
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
