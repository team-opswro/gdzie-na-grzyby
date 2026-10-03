// Nazwy miejsc (oddział / leśnictwo / nadleśnictwo) i linki nawigacji. Moduł czysty.

export function oddzKey(id) {
  const parts = String(id).split("-");
  return parts.length >= 5 ? parts.slice(0, 5).join("-") : null;
}

export function placeName(id, nazwy) {
  const parts = String(id).split("-");
  const lesnKey = parts.slice(0, 4).join("-");
  const nadlKey = parts.slice(0, 2).join("-");
  return {
    oddz: parts[4] ?? "",
    lesn: nazwy?.lesn?.[lesnKey] ?? null,
    nadl: nazwy?.nadl?.[nadlKey] ?? null,
    lesnKey,
  };
}

export function formatPlace(id, nazwy) {
  const p = placeName(id, nazwy);
  if (!p.lesn && !p.nadl) return `Oddz. ${p.oddz} · ${p.lesnKey}`;
  const out = [`Oddz. ${p.oddz}`];
  if (p.lesn) out.push(`Leśn. ${p.lesn}`);
  if (p.nadl) out.push(`Nadl. ${p.nadl}`);
  return out.join(" · ");
}

export function navUrls(lat, lon) {
  const la = Number(lat).toFixed(5);
  const lo = Number(lon).toFixed(5);
  return {
    google: `https://www.google.com/maps/dir/?api=1&destination=${la},${lo}`,
    osm: `https://www.openstreetmap.org/directions?route=%3B${la}%2C${lo}`,
  };
}
