import { score, scoreClass, weatherFor, bestFor, toWet, SPECIES, ALL } from "./data.js";
import { chartData, chartDataBy, trend, trendBy, renderChart, DOW } from "./chart.js";
import { CLASS_LABELS, COLORS } from "./map.js";
import { formatPlace, navUrls } from "./names.js";

const pct = (x) => Math.round(x * 100) + "%";

function el(tag, text, className) {
  const e = document.createElement(tag);
  if (text != null) e.textContent = text;
  if (className) e.className = className;
  return e;
}

function row(table, label, value) {
  const tr = document.createElement("tr");
  tr.append(el("th", label), el("td", value));
  table.append(tr);
}

export const ZAKAZY_URL = "https://zakazywstepu.bdl.lasy.gov.pl/zakazy/";

export function reserveText(rez) {
  const name = rez && rez !== "rezerwat" ? ` „${rez}”` : "";
  return `Rezerwat przyrody${name} — zbieranie grzybów jest co do zasady zabronione.`;
}

export function zakazyLink() {
  const a = el("a", "Sprawdź aktualne zakazy wstępu (BDL)", "popup-zakazy");
  a.href = ZAKAZY_URL;
  a.target = "_blank";
  a.rel = "noopener";
  const p = el("p", null, "popup-link");
  p.append(a);
  return p;
}

export function renderReserve(name, withLink = true) {
  const n = typeof name === "string" ? name.trim() : "";
  const box = el("div", reserveText(n || "rezerwat"), "popup-score popup-reserve");
  box.style.borderLeftColor = COLORS.reserve;
  if (!withLink) return box;
  const wrap = el("div", null, "popup-reserve-wrap");
  wrap.append(box, zakazyLink());
  return wrap;
}

export const LIM_TEXT = {
  dry: "Ogranicza: za mało deszczu",
  dry_soil: "Ogranicza: przesuszone podłoże",
  cold: "Ogranicza: za zimna gleba",
  hot: "Ogranicza: za ciepła gleba",
  season: "Ogranicza: poza sezonem",
  frost: "Ogranicza: niedawny przymrozek",
};
// „Słabe strony siedliska” (atrybut hl_<gatunek> w kafelkach, spec J §3).
export const HAB_LIM_TEXT = {
  veg: "Ogranicza siedlisko: gęste runo/zadarnienie",
  moist: "Ogranicza siedlisko: zbyt mokre (bagienne)",
  degr: "Ogranicza siedlisko: siedlisko zniekształcone",
  soil: "Ogranicza siedlisko: mniej korzystna gleba",
  damage: "Ogranicza siedlisko: uszkodzony drzewostan",
  density: "Ogranicza siedlisko: zadrzewienie (za rzadko lub za gęsto)",
  twi: "Ogranicza siedlisko: położenie (za sucho lub za mokro)",
  exposure: "Ogranicza siedlisko: stromy stok południowy",
  habitat: "Ogranicza siedlisko: typ siedliskowy mniej korzystny",
  age: "Ogranicza siedlisko: wiek drzewostanu",
};
// Wilgotność miejsca (spec L): atrybuty wet (0–100) i wl (powód) w kafelkach.
export const WET_REASON = {
  water: "blisko wody", ditch: "przy rowie lub strumieniu", valley: "w obniżeniu terenu",
  soil: "wilgotna gleba", habitat: "wilgotne siedlisko", twi: "spływ wody z okolicy",
  hilltop: "wyniesienie, woda spływa", dry: "z dala od wody, suche podłoże",
};
const WET_HIGH = 65;
const WET_LOW = 35;
const WET_NOTE_MIN = 0.05; // minimalna różnica w_eff − w, przy której popup komentuje suszę

export function wetLabel(wet, wl) {
  const x = toWet(wet);
  if (x == null) return null;
  const level = x >= WET_HIGH ? "wysoka" : x <= WET_LOW ? "niska" : "średnia";
  const why = WET_REASON[wl];
  return `Wilgotność miejsca: ${level}${why ? ` (${why})` : ""}`;
}

// Zdanie o suszy, gdy dzień ogranicza opad, a korekta jest wyraźna; null w pozostałych przypadkach.
export function droughtNote(weather) {
  if (!weather || weather.w_raw == null || !["dry", "dry_soil"].includes(weather.lim)) return null;
  const d = weather.w - weather.w_raw;
  if (Math.abs(d) < WET_NOTE_MIN) return null;
  return d > 0 ? "W suszy to miejsce wypada lepiej niż okolica — trzyma wilgoć."
    : "W suszy to miejsce wypada gorzej niż okolica — szybko przesycha.";
}

export const SOIL_DRY = 0.15;
export const SOIL_WET = 0.3;

export function moistureLabel(m) {
  return m < SOIL_DRY ? "sucha" : m < SOIL_WET ? "umiarkowana" : "wilgotna";
}

const dec = (x) => x.toFixed(1).replace(".", ",");

// „Borowik szlachetny” -> „borowik”
export function shortName(name) {
  return String(name ?? "").split(/\s+/)[0].toLowerCase();
}

export function rankLabel(group, nazwy, speciesList = SPECIES) {
  let line1 = formatPlace(group.best.id, nazwy);
  if (group.species) {
    const sp = speciesList.find((x) => x.key === group.species);
    line1 += ` · ${shortName(sp?.name ?? group.species)}`;
  }
  return {
    line1,
    line2: group.drive
      ? `${dec(group.drive.meters / 1000)} km autem · ok. ${Math.ceil(group.drive.seconds / 60)} min · parking ${dec(group.drive.parking.forestDistanceKm)} km od miejsca (linia prosta)${group.drive.parking.fee === "yes" ? " · płatny" : ""}`
      : `${dec(group.distanceKm)} km ${group.bearing} · ${group.count} wydz.`,
  };
}

export function actionLinks(lat, lon) {
  const urls = navUrls(lat, lon);
  const row = el("div", null, "popup-actions");
  const go = el("a", "Prowadź", "popup-action popup-go");
  go.href = urls.google;
  go.target = "_blank";
  go.rel = "noopener";
  const osm = el("a", "OSM", "popup-action popup-osm");
  osm.href = urls.osm;
  osm.target = "_blank";
  osm.rel = "noopener";
  row.append(go, osm);
  return row;
}

export function renderParking(props, lngLat) {
  const root = el("div", null, "popup popup-parking");
  const title = el("div", "Parking", "popup-score");
  title.style.borderLeftColor = "#1a237e";
  root.append(title);
  if (props.name) root.append(el("div", props.name, "popup-place"));
  if (props.fee === "yes") root.append(el("div", "płatny", "popup-fee"));
  else if (props.fee === "no") root.append(el("div", "bezpłatny", "popup-fee"));
  root.append(actionLinks(lngLat.lat, lngLat.lng));
  return root;
}

const DRY_DAYS_NOTE = 3; // od tylu dni bez deszczu popup dopisuje „bez deszczu od N dni”

export function formatWx(wx) {
  // Z bilansem wody (spec M) wilgotność opisuje wiersz zapasu; etykieta z wilgotności Open-Meteo by mu przeczyła.
  const hasWater = wx.water != null;
  const out = {
    rain: `Deszcz (5–21 dni wcześniej): ${dec(wx.rain_mm)} mm`,
    soil: hasWater ? `Gleba: ${dec(wx.soil_t)} °C` : `Gleba: ${dec(wx.soil_t)} °C, ${moistureLabel(wx.soil_m)}`,
  };
  if (hasWater) {
    const dry = wx.dry_days >= DRY_DAYS_NOTE ? ` · bez deszczu od ${wx.dry_days} dni` : "";
    out.water = `Zapas wody w podłożu: ${Math.round(wx.water * 100)}%${dry}`;
  }
  if (wx.et0_mm != null) {
    out.et0 = `Parowanie (5–21 dni): ${dec(wx.et0_mm)} mm`;
  }
  return out;
}

export function trendArrow(dir) {
  return dir === "up" ? "↑" : dir === "down" ? "↓" : dir === "flat" ? "→" : "";
}

export function trendLabel(t) {
  if (!t || !t.dir) return "";
  const word = t.dir === "up" ? "rośnie" : t.dir === "down" ? "spada" : "bez zmian";
  return `${word}, ${t.delta > 0 ? "+" : ""}${t.delta}`;
}

// Lista gatunków trybu „all”: malejąco po wyniku dnia (bez pogody — po h).
function speciesBars(props, list, pogoda, dayIdx) {
  const wet = toWet(props.wet);
  const items = list.map((sp) => {
    const h = Number(props["h_" + sp.key] ?? 0);
    const wf = pogoda ? weatherFor(pogoda, props.cell, sp.key, dayIdx, wet) : null;
    const value = pogoda ? (wf ? score(h, wf.w) : null) : h;
    return { sp, value };
  });
  items.sort((a, b) => (b.value ?? -1) - (a.value ?? -1));
  const ul = el("ul", null, "popup-species");
  for (const { sp, value } of items) {
    const li = el("li");
    li.append(el("span", shortName(sp.name), "ps-name"));
    const bar = el("span", null, "ps-bar");
    const fill = el("i");
    fill.style.width = `${Math.max(0, Math.min(100, value ?? 0))}%`;
    if (value != null) fill.style.background = COLORS.classes[scoreClass(value)];
    bar.append(fill);
    li.append(bar, el("span", value == null ? "–" : pogoda ? String(value) : pct(value / 100), "ps-val"));
    ul.append(li);
  }
  return ul;
}

export function renderPopup(props, ctx) {
  const { pogoda = null, dayIdx, todayIso, onDaySelect, nazwy = null, lngLat = null, onShare = null, speciesList = SPECIES } = ctx;
  // ctx.keys: gatunki wyboru (grupa lub wszystkie); bez nich — z ctx.species ("all" albo jeden klucz).
  const keys = ctx.keys ?? (ctx.species === ALL ? speciesList.map((s) => s.key) : [ctx.species]);
  const isAll = keys.length > 1;
  const listed = keys.map((k) => speciesList.find((s) => s.key === k) ?? { key: k, name: k });
  const hAll = {};
  // brak atrybutu h_* w kafelku = 0 (zera nie są zapisywane)
  for (const k of keys) hAll[k] = Number(props["h_" + k] ?? 0);
  const wet = toWet(props.wet); // wilgotność miejsca (spec L), brak = bez korekty
  const best = isAll && pogoda ? bestFor(pogoda, props.cell, hAll, dayIdx, wet) : null;
  let species = keys[0];
  if (isAll) {
    species = best?.species ?? keys.reduce((a, k) => (hAll[k] > hAll[a] ? k : a), keys[0]);
  }
  const scoreAtAll = (idx) => (idx < 0 ? null : bestFor(pogoda, props.cell, hAll, idx, wet)?.score ?? null);
  const root = el("div", null, "popup");
  if (props.id) {
    root.append(el("div", formatPlace(props.id, nazwy), "popup-place"));
    root.append(el("div", props.id, "popup-id"));
  } else {
    root.append(el("div", "—", "popup-id"));
  }

  const h = Number(props["h_" + species] ?? 0);
  const weather = pogoda ? weatherFor(pogoda, props.cell, species, dayIdx, wet) : null;
  if (props.rez) {
    root.append(renderReserve(props.rez, false)); // link dodaje koniec popupu
  } else {
    const s = weather ? score(h, weather.w) : null;
    if (s != null) {
      const badge = el("div", null, "popup-score");
      const who = isAll ? ` · ${shortName(speciesList.find((x) => x.key === species)?.name ?? species)}` : "";
      badge.append(`Wynik: ${s}/100 (${CLASS_LABELS[scoreClass(s)]})${who}`);
      badge.style.borderLeftColor = COLORS.classes[scoreClass(s)];
      const tr = isAll ? trendBy(pogoda, scoreAtAll, dayIdx) : trend(pogoda, props.cell, species, h, dayIdx, wet);
      if (tr.dir) {
        const arrow = el("span", " " + trendArrow(tr.dir), "popup-trend");
        arrow.title = `${tr.delta > 0 ? "+" : ""}${tr.delta} względem poprzedniego dnia`;
        arrow.setAttribute("aria-label", trendLabel(tr));
        badge.append(arrow);
      }
      if (tr.peak) {
        badge.append(el("div", `Szczyt: ${DOW[new Date(`${tr.peak.date}T00:00:00Z`).getUTCDay()]}. (${tr.peak.score})`, "popup-peak"));
      }
      root.append(badge);
      if (weather.lim && LIM_TEXT[weather.lim]) root.append(el("div", LIM_TEXT[weather.lim], "popup-lim"));
      const note = droughtNote(weather);
      if (note) root.append(el("div", note, "popup-lim popup-wet"));
    } else {
      root.append(el("div", "Brak danych pogodowych dla tego miejsca", "popup-score popup-nodata"));
    }
    if (isAll) root.append(speciesBars(props, listed, pogoda, dayIdx));
    if (pogoda && todayIso) {
      const data = isAll ? chartDataBy(pogoda, scoreAtAll, todayIso) : chartData(pogoda, props.cell, species, h, todayIso, wet);
      if (data.length) {
        const box = el("div", null, "popup-chart");
        box.append(renderChart(data, dayIdx, onDaySelect || (() => {})));
        root.append(box);
      }
    }
  }

  if (!props.rez && lngLat) {
    const actions = actionLinks(lngLat.lat, lngLat.lng);
    if (onShare) {
      const sh = el("button", "Udostępnij miejsce", "popup-action popup-share");
      sh.type = "button";
      sh.id = "popup-share-place";
      sh.addEventListener("click", () => onShare(props, lngLat));
      actions.append(sh);
    }
    root.append(actions);
  }

  const t = document.createElement("table");
  row(t, "Gatunek panujący", props.sp || "—");
  row(t, "Wiek", props.age != null && props.age !== "" ? props.age + " lat" : "—");
  row(t, "Typ siedliskowy", props.hab || "—");
  row(t, "Siedlisko", pct(h / 100));
  const weak = !isAll ? HAB_LIM_TEXT[props["hl_" + species]] : null;
  if (weak && !props.rez) {
    const tr = document.createElement("tr");
    const td = el("td", weak, "popup-hablim");
    td.colSpan = 2;
    tr.append(td);
    t.append(tr);
  }
  const wetText = !props.rez ? wetLabel(wet, props.wl) : null;
  if (wetText) {
    const tr = document.createElement("tr");
    const td = el("td", wetText, "popup-wetness");
    td.colSpan = 2;
    tr.append(td);
    t.append(tr);
  }
  if (weather && weather.wx && !props.rez) {
    const f = formatWx(weather.wx);
    for (const line of [f.rain, f.water, f.soil, f.et0]) {
      if (line == null) continue;
      const r = document.createElement("tr");
      const c = el("td", line);
      c.colSpan = 2;
      r.append(c);
      t.append(r);
    }
  }
  root.append(t);
  if (weather && !props.rez) {
    const d = el("details", null, "popup-details");
    d.append(el("summary", "Szczegóły modelu"));
    const dt = document.createElement("table");
    row(dt, "Opad", pct(weather.rain));
    if (typeof weather.moist === "number") row(dt, "Wilgotność podłoża", pct(weather.moist));
    row(dt, "Temperatura", pct(weather.temp));
    row(dt, "Sezon", pct(weather.season));
    if (typeof weather.pulse === "number") {
      row(dt, "Ochłodzenie", `+${Math.round((weather.pulse - 1) * 100)}%`);
    }
    if (typeof weather.frost === "number") {
      row(dt, "Przymrozek", pct(weather.frost));
    }
    if (weather.w_raw != null) {
      const d = Math.round((weather.w - weather.w_raw) * 100);
      row(dt, "Wilgotność miejsca", `${Math.round(weather.wet)}/100 (${d > 0 ? "+" : ""}${d} pkt %)`);
    }
    d.append(dt);
    root.append(d);
  }
  root.append(zakazyLink());
  return root;
}
