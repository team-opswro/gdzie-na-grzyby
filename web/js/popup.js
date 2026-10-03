import { score, scoreClass } from "./data.js";
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

export function renderPopup(props, weather, speciesKey) {
  const root = el("div", null, "popup");
  root.append(el("div", props.id || "—", "popup-id"));

  const h = Number(props["h_" + speciesKey] ?? 0);
  const s = weather ? score(h, weather.w) : null;
  if (s != null) {
    const badge = el("div", `Wynik: ${s}/100 (${CLASS_LABELS[scoreClass(s)]})`, "popup-score");
    badge.style.borderLeftColor = COLORS.classes[scoreClass(s)];
    root.append(badge);
  } else {
    root.append(el("div", "Brak danych pogodowych dla tego miejsca", "popup-score popup-nodata"));
  }

  const t = document.createElement("table");
  row(t, "Gatunek panujący", props.sp || "—");
  row(t, "Wiek", props.age != null && props.age !== "" ? props.age + " lat" : "—");
  row(t, "Typ siedliskowy", props.hab || "—");
  row(t, "Siedlisko", pct(h / 100));
  if (weather) {
    row(t, "Opad", pct(weather.rain));
    row(t, "Temperatura", pct(weather.temp));
    row(t, "Sezon", pct(weather.season));
  }
  root.append(t);
  return root;
}
