import { SPECIES, loadData, weatherFor, availableDays, bannerText } from "./data.js";
import { topN } from "./ranking.js";
import { parseHash, formatHash } from "./hash.js";
import { createMap, setView, COLORS, CLASS_LABELS, FILL_OPACITY } from "./map.js";
import { renderPopup } from "./popup.js";

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
  const state = { species: hash.species, day: hash.day };
  let data = { pogoda: null, centroids: null };
  let days = []; // availableDays(...) — pozycja w tej tablicy to „day” w hashu
  let gps = null; // {lat, lon} po zgodzie na lokalizację
  let popup = null;
  let mapReady = false;
  let loaded = false;

  const sel = $("species");
  for (const s of SPECIES) sel.append(new Option(s.name, s.key));
  sel.value = state.species;
  buildLegend();

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
    onFeatureClick: (props, lngLat) => showPopup(props, lngLat),
    onMove: () => {
      writeHash();
      if (!gps) updateRanking();
    },
  });
  map.on("load", () => { mapReady = true; setView(map, effective, state.species, dayIdx()); });

  function showPopup(props, lngLat) {
    popup?.remove();
    const wx = effective ? weatherFor(effective, props.cell, state.species, dayIdx()) : null;
    const content = renderPopup(props, wx, state.species);
    popup = new maplibregl.Popup({ maxWidth: "280px" }).setLngLat(lngLat).setDOMContent(content).addTo(map);
  }

  function writeHash() {
    const c = map.getCenter();
    history.replaceState(null, "", formatHash({ species: state.species, day: state.day, zoom: map.getZoom(), center: [c.lng, c.lat] }));
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
    const top = topN(centroids, effective, state.species, dayIdx(), origin());
    if (!top.length) {
      list.append(li("Brak miejsc o dodatnim wyniku w promieniu 20 km", "empty"));
      return;
    }
    top.forEach((r, i) => {
      const item = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      const sc = document.createElement("span");
      sc.className = "rank-score";
      sc.textContent = r.score;
      const name = document.createElement("span");
      name.className = "rank-name";
      name.textContent = `${i + 1}. ${r.id}`;
      const dist = document.createElement("span");
      dist.className = "rank-dist";
      dist.textContent = `${r.distanceKm.toString().replace(".", ",")} km`;
      btn.append(sc, name, dist);
      btn.addEventListener("click", () => flyToRow(r));
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

  $("locate").addEventListener("click", () => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        gps = { lat: pos.coords.latitude, lon: pos.coords.longitude };
        map.flyTo({ center: [gps.lon, gps.lat], zoom: Math.max(map.getZoom(), 12) });
        updateRanking();
      },
      () => { gps = null; $("locate").title = "Brak zgody na lokalizację — ranking od środka mapy"; },
      { enableHighAccuracy: false, timeout: 10000 },
    );
  });

  function setPanelOpen(open) {
    $("panel").classList.toggle("open", open);
    $("panel-toggle").setAttribute("aria-expanded", String(open));
  }
  $("panel-toggle").addEventListener("click", () => setPanelOpen(!$("panel").classList.contains("open")));

  updateDayControls();
  data = await loadData();
  ({ pogoda, centroids } = data);
  if (pogoda) days = availableDays(pogoda.days, todayLocalIso());
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
  return map;
}

function buildLegend() {
  const box = $("legend");
  const add = (color, text, opacity) => {
    const s = document.createElement("span");
    const sw = document.createElement("i");
    sw.style.background = color;
    if (opacity) sw.style.opacity = String(opacity);
    s.append(sw, text);
    box.append(s);
  };
  COLORS.classes.forEach((c, i) => add(c, CLASS_LABELS[i], i === 0 ? FILL_OPACITY.weak : FILL_OPACITY.normal));
  add(COLORS.noData, "brak danych", FILL_OPACITY.noData);
}
