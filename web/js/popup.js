import { score, scoreClass, weatherFor, bestFor, SPECIES, ALL } from "./data.js";
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
  dry_soil: "Ogranicza: przesuszona gleba",
  cold: "Ogranicza: za zimna gleba",
  hot: "Ogranicza: za ciepła gleba",
  season: "Ogranicza: poza sezonem",
  frost: "Ogranicza: niedawny przymrozek",
};
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
    line2: `${dec(group.distanceKm)} km ${group.bearing} · ${group.count} wydz.`,
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

export function formatWx(wx) {
  const out = {
    rain: `Deszcz (5–21 dni wcześniej): ${dec(wx.rain_mm)} mm`,
    soil: `Gleba: ${dec(wx.soil_t)} °C, ${moistureLabel(wx.soil_m)}`,
  };
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
  const items = list.map((sp) => {
    const h = Number(props["h_" + sp.key] ?? 0);
    const wf = pogoda ? weatherFor(pogoda, props.cell, sp.key, dayIdx) : null;
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
  const best = isAll && pogoda ? bestFor(pogoda, props.cell, hAll, dayIdx) : null;
  let species = keys[0];
  if (isAll) {
    species = best?.species ?? keys.reduce((a, k) => (hAll[k] > hAll[a] ? k : a), keys[0]);
  }
  const scoreAtAll = (idx) => (idx < 0 ? null : bestFor(pogoda, props.cell, hAll, idx)?.score ?? null);
  const root = el("div", null, "popup");
  if (props.id) {
    root.append(el("div", formatPlace(props.id, nazwy), "popup-place"));
    root.append(el("div", props.id, "popup-id"));
  } else {
    root.append(el("div", "—", "popup-id"));
  }

  const h = Number(props["h_" + species] ?? 0);
  const weather = pogoda ? weatherFor(pogoda, props.cell, species, dayIdx) : null;
  if (props.rez) {
    root.append(renderReserve(props.rez, false)); // link dodaje koniec popupu
  } else {
    const s = weather ? score(h, weather.w) : null;
    if (s != null) {
      const badge = el("div", null, "popup-score");
      const who = isAll ? ` · ${shortName(speciesList.find((x) => x.key === species)?.name ?? species)}` : "";
      badge.append(`Wynik: ${s}/100 (${CLASS_LABELS[scoreClass(s)]})${who}`);
      badge.style.borderLeftColor = COLORS.classes[scoreClass(s)];
      const tr = isAll ? trendBy(pogoda, scoreAtAll, dayIdx) : trend(pogoda, props.cell, species, h, dayIdx);
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
    } else {
      root.append(el("div", "Brak danych pogodowych dla tego miejsca", "popup-score popup-nodata"));
    }
    if (isAll) root.append(speciesBars(props, listed, pogoda, dayIdx));
    if (pogoda && todayIso) {
      const data = isAll ? chartDataBy(pogoda, scoreAtAll, todayIso) : chartData(pogoda, props.cell, species, h, todayIso);
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
  if (weather && weather.wx && !props.rez) {
    const f = formatWx(weather.wx);
    for (const line of [f.rain, f.soil, f.et0]) {
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
    row(dt, "Temperatura", pct(weather.temp));
    row(dt, "Sezon", pct(weather.season));
    if (typeof weather.pulse === "number") {
      row(dt, "Ochłodzenie", `+${Math.round((weather.pulse - 1) * 100)}%`);
    }
    if (typeof weather.frost === "number") {
      row(dt, "Przymrozek", pct(weather.frost));
    }
    d.append(dt);
    root.append(d);
  }
  root.append(zakazyLink());
  return root;
}
