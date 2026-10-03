export const RISK_COLORS = { niejadalny: "#fdd835", trujący: "#fb8c00", "śmiertelnie trujący": "#d32f2f" };
export const DISCLAIMER = "Nie zbieraj grzybów, których nie znasz. W razie wątpliwości skorzystaj z punktu grzyboznawczego (Sanepid).";
export const UNREVIEWED_TEXT = "Opis nie został jeszcze zweryfikowany przez grzyboznawcę.";
export const NO_INFO_TEXT = "Brak opisu gatunku";

const MONTHS = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"];

function md(s) {
  const [m, d] = String(s).split("-").map(Number);
  return `${d} ${MONTHS[m - 1]}`;
}

export function speciesCardModel(info, key) {
  const s = info?.species?.find((x) => x.key === key);
  if (!s) return null;
  return {
    title: s.name,
    latin: s.latin,
    season: `${md(s.season.start)} – ${md(s.season.end)}`,
    partners: (s.partners ?? []).join(", "),
    preferred: (s.habitats_preferred ?? []).join(", "),
    adjacent: (s.habitats_adjacent ?? []).join(", "),
    age: `od ${s.age_min} lat`,
    description: s.description,
    lookalikes: s.lookalikes ?? [],
    wiki: s.wiki,
    unreviewed: info.reviewed !== true,
  };
}

export function aboutForecastText(generatedAt) {
  const d = generatedAt ? new Date(generatedAt) : null;
  if (!d || Number.isNaN(d.getTime())) return "brak prognozy";
  const p = (n) => String(n).padStart(2, "0");
  return `Prognoza z: ${d.getDate()} ${MONTHS[d.getMonth()]}, ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function el(tag, text, cls) {
  const e = document.createElement(tag);
  if (text != null) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}

export function renderSpeciesCard(model) {
  const root = el("div", null, "card");
  if (!model) {
    root.append(el("p", NO_INFO_TEXT));
    return root;
  }
  const h = el("h2", model.title);
  h.append(" ", el("i", model.latin, "card-latin"));
  h.id = "species-card-title";
  root.append(h);
  if (model.unreviewed) root.append(el("p", UNREVIEWED_TEXT, "card-unreviewed"));
  const dl = el("dl", null, "card-facts");
  const fact = (k, v) => { if (v) dl.append(el("dt", k), el("dd", v)); };
  fact("Sezon", model.season);
  fact("Drzewa", model.partners);
  fact("Siedliska preferowane", model.preferred);
  fact("Siedliska sąsiednie", model.adjacent);
  fact("Wiek drzewostanu", model.age);
  root.append(dl, el("p", model.description));
  root.append(el("h3", "Nie pomyl z"));
  if (!model.lookalikes.length) root.append(el("p", "Brak groźnych sobowtórów."));
  else {
    const ul = el("ul", null, "card-looks");
    for (const l of model.lookalikes) {
      const li = el("li");
      const tag = el("span", l.risk, "risk");
      tag.style.background = RISK_COLORS[l.risk] ?? "#ccc";
      tag.style.color = l.risk === "śmiertelnie trujący" ? "#fff" : "#222";
      li.append(el("b", l.name), " ", el("i", l.latin), " ", tag, el("div", l.how));
      ul.append(li);
    }
    root.append(ul);
  }
  if (typeof model.wiki === "string" && model.wiki.startsWith("https://")) {
    const a = el("a", "Więcej w Wikipedii");
    a.href = model.wiki;
    a.target = "_blank";
    a.rel = "noopener";
    const p = el("p");
    p.append(a);
    root.append(p);
  }
  root.append(el("p", DISCLAIMER, "card-disclaimer"));
  return root;
}
