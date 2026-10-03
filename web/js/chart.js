import { availableDays, weatherFor, score, scoreClass } from "./data.js";
import { COLORS } from "./map.js";

export const DOW = ["nd", "pn", "wt", "śr", "czw", "pt", "sob"];
const MONTHS = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"];
const MAX_DAYS = 7;
const TREND_THRESHOLD = 5;
const PEAK_MARGIN = 5;

function scoreAt(pogoda, cell, species, h, idx) {
  if (idx < 0) return null;
  const wf = weatherFor(pogoda, cell, species, idx);
  return wf ? score(h, wf.w) : null;
}

export function chartData(pogoda, cell, species, h, todayIso) {
  return availableDays(pogoda.days, todayIso)
    .slice(0, MAX_DAYS)
    .map(({ date, idx }) => {
      const s = scoreAt(pogoda, cell, species, h, idx);
      return { date, idx, score: s, cls: scoreClass(s) };
    });
}

export function trend(pogoda, cell, species, h, dayIdx) {
  const cur = scoreAt(pogoda, cell, species, h, dayIdx);
  const prev = scoreAt(pogoda, cell, species, h, dayIdx - 1);
  let dir = null;
  let delta = null;
  if (cur != null && prev != null) {
    delta = cur - prev;
    dir = delta >= TREND_THRESHOLD ? "up" : delta <= -TREND_THRESHOLD ? "down" : "flat";
  }
  let peak = null;
  if (cur != null) {
    pogoda.days.forEach((date, idx) => {
      if (idx <= dayIdx) return;
      const s = scoreAt(pogoda, cell, species, h, idx);
      if (s != null && s >= cur + PEAK_MARGIN && (peak == null || s > peak.score)) peak = { idx, date, score: s };
    });
  }
  return { dir, delta, peak };
}

function dayParts(iso) {
  const d = new Date(`${iso}T00:00:00Z`);
  return { dow: DOW[d.getUTCDay()], day: d.getUTCDate(), month: MONTHS[d.getUTCMonth()] };
}

const W = 252;
const H = 90;
const BAR_AREA = 52; // maks. wysokość słupka
const BASE = 66;     // linia podstawy słupków
const MAX_SCORE = 100;

export function renderChart(data, selectedIdx, onSelect) {
  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs = {}) => {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    return e;
  };
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", role: "group", "aria-label": "Prognoza na 7 dni" });
  const slot = W / MAX_DAYS;
  const barW = Math.floor(slot * 0.6);
  data.forEach((d, i) => {
    const { dow, day, month } = dayParts(d.date);
    const x = i * slot + (slot - barW) / 2;
    const cx = i * slot + slot / 2;
    const selected = d.idx === selectedIdx;
    const g = el("g", {
      role: "button",
      tabindex: "0",
      "aria-label": `${dow}. ${day} ${month}: ${d.score == null ? "brak danych" : d.score}`,
      style: "cursor:pointer;outline:none",
    });
    const hasData = d.score != null;
    const bh = hasData ? Math.max(2, Math.round((Math.min(d.score, MAX_SCORE) / MAX_SCORE) * BAR_AREA)) : BAR_AREA / 3;
    const rect = el("rect", {
      x, y: BASE - bh, width: barW, height: bh, rx: 2,
      fill: hasData ? COLORS.classes[d.cls] : "none",
      stroke: selected ? "#111" : hasData ? "none" : COLORS.noData,
      "stroke-width": selected ? 2 : 1,
    });
    if (!hasData) rect.setAttribute("stroke-dasharray", "3 2");
    g.appendChild(rect);
    const val = el("text", { x: cx, y: BASE - bh - 3, "text-anchor": "middle", "font-size": 10, fill: "currentColor" });
    val.textContent = hasData ? String(d.score) : "–";
    g.appendChild(val);
    const lab = el("text", {
      x: cx, y: BASE + 12, "text-anchor": "middle", "font-size": 10, fill: "currentColor",
      "font-weight": selected ? "700" : "400",
    });
    lab.textContent = dow;
    g.appendChild(lab);
    const sub = el("text", { x: cx, y: BASE + 23, "text-anchor": "middle", "font-size": 8, fill: "currentColor", opacity: 0.6 });
    sub.textContent = `${day}.${String(new Date(`${d.date}T00:00:00Z`).getUTCMonth() + 1).padStart(2, "0")}`;
    g.appendChild(sub);
    g.addEventListener("click", () => onSelect(d.idx));
    g.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onSelect(d.idx);
      }
    });
    svg.appendChild(g);
  });
  return svg;
}
