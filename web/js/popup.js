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

export const ZAKAZY_URL = "https://www.bdl.lasy.gov.pl/portal/zakazy-wstepu";

export function reserveText(rez) {
  const name = rez && rez !== "rezerwat" ? ` „${rez}”` : "";
  return `Rezerwat przyrody${name} — zbieranie grzybów jest co do zasady zabronione.`;
}

function zakazyLink() {
  const a = el("a", "Sprawdź aktualne zakazy wstępu (BDL)", "popup-zakazy");
  a.href = ZAKAZY_URL;
  a.target = "_blank";
  a.rel = "noopener";
  const p = el("p", null, "popup-link");
  p.append(a);
  return p;
}

export function renderReserve(name) {
  const n = typeof name === "string" ? name.trim() : "";
  const box = el("div", reserveText(n || "rezerwat"), "popup-score popup-reserve");
  box.style.borderLeftColor = COLORS.reserve;
  return box;
}

export function renderPopup(props, weather, speciesKey) {
  const root = el("div", null, "popup");
  root.append(el("div", props.id || "—", "popup-id"));

  const h = Number(props["h_" + speciesKey] ?? 0);
  if (props.rez) {
    weather = null;
    root.append(renderReserve(props.rez));
  }
  const s = weather ? score(h, weather.w) : null;
  if (props.rez) {
    // ramka rezerwatu pokazana wyżej, zamiast wyniku
  } else if (s != null) {
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
  root.append(zakazyLink());
  return root;
}
