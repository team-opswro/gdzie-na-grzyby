import { score, scoreClass, weatherFor } from "./data.js";
import { chartData, trend, renderChart, DOW } from "./chart.js";
import { CLASS_LABELS, COLORS } from "./map.js";

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
};
export const SOIL_DRY = 0.15;
export const SOIL_WET = 0.3;

export function moistureLabel(m) {
  return m < SOIL_DRY ? "sucha" : m < SOIL_WET ? "umiarkowana" : "wilgotna";
}

const dec = (x) => x.toFixed(1).replace(".", ",");

export function formatWx(wx) {
  return {
    rain: `Deszcz (5–21 dni wcześniej): ${dec(wx.rain_mm)} mm`,
    soil: `Gleba: ${dec(wx.soil_t)} °C, ${moistureLabel(wx.soil_m)}`,
  };
}

export function trendArrow(dir) {
  return dir === "up" ? "↑" : dir === "down" ? "↓" : dir === "flat" ? "→" : "";
}

export function renderPopup(props, ctx) {
  const { pogoda = null, species, dayIdx, todayIso, onDaySelect } = ctx;
  const root = el("div", null, "popup");
  root.append(el("div", props.id || "—", "popup-id"));

  const h = Number(props["h_" + species] ?? 0);
  const weather = pogoda ? weatherFor(pogoda, props.cell, species, dayIdx) : null;
  if (props.rez) {
    root.append(renderReserve(props.rez, false)); // link dodaje koniec popupu
  } else {
    const s = weather ? score(h, weather.w) : null;
    if (s != null) {
      const badge = el("div", null, "popup-score");
      badge.append(`Wynik: ${s}/100 (${CLASS_LABELS[scoreClass(s)]})`);
      badge.style.borderLeftColor = COLORS.classes[scoreClass(s)];
      const tr = trend(pogoda, props.cell, species, h, dayIdx);
      if (tr.dir) {
        const arrow = el("span", " " + trendArrow(tr.dir), "popup-trend");
        arrow.title = `${tr.delta > 0 ? "+" : ""}${tr.delta} względem poprzedniego dnia`;
        badge.append(arrow);
      }
      if (tr.peak) {
        badge.append(el("div", `Szczyt: ${DOW[new Date(`${tr.peak.date}T00:00:00Z`).getUTCDay()]}. (${tr.peak.score})`, "popup-peak"));
      }
      root.append(badge);
      if (weather.lim) root.append(el("div", LIM_TEXT[weather.lim], "popup-lim"));
    } else {
      root.append(el("div", "Brak danych pogodowych dla tego miejsca", "popup-score popup-nodata"));
    }
    if (pogoda && todayIso) {
      const data = chartData(pogoda, props.cell, species, h, todayIso);
      if (data.length) {
        const box = el("div", null, "popup-chart");
        box.append(renderChart(data, dayIdx, onDaySelect || (() => {})));
        root.append(box);
      }
    }
  }

  const t = document.createElement("table");
  row(t, "Gatunek panujący", props.sp || "—");
  row(t, "Wiek", props.age != null && props.age !== "" ? props.age + " lat" : "—");
  row(t, "Typ siedliskowy", props.hab || "—");
  row(t, "Siedlisko", pct(h / 100));
  if (weather && weather.wx && !props.rez) {
    const f = formatWx(weather.wx);
    const r1 = document.createElement("tr");
    const c1 = el("td", f.rain);
    c1.colSpan = 2;
    r1.append(c1);
    const r2 = document.createElement("tr");
    const c2 = el("td", f.soil);
    c2.colSpan = 2;
    r2.append(c2);
    t.append(r1, r2);
  }
  root.append(t);
  if (weather && !props.rez) {
    const d = el("details", null, "popup-details");
    d.append(el("summary", "Szczegóły modelu"));
    const dt = document.createElement("table");
    row(dt, "Opad", pct(weather.rain));
    row(dt, "Temperatura", pct(weather.temp));
    row(dt, "Sezon", pct(weather.season));
    d.append(dt);
    root.append(d);
  }
  root.append(zakazyLink());
  return root;
}
