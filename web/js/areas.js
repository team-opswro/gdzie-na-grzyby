// Gotowe widoki dla lasów obecnych w zbiorze BDL; współrzędne w kolejności lon, lat.
export const AREAS = {
  wroclaw: { name: "Wrocław i okolice", center: [17.033, 51.11], zoom: 10 },
  miekinia: { name: "Miękinia", center: [16.739, 51.192], zoom: 12 },
  oborniki: { name: "Oborniki Śląskie", center: [16.914, 51.302], zoom: 12 },
  olesnica: { name: "Oleśnica Śląska", center: [17.381, 51.21], zoom: 11 },
  olawa: { name: "Oława", center: [17.31, 50.947], zoom: 11 },
  milicz: { name: "Milicz", center: [17.271, 51.527], zoom: 12 },
  twardogora: { name: "Twardogóra", center: [17.468, 51.365], zoom: 12 },
  opole: { name: "Opole", center: [17.9, 50.65], zoom: 10 },
};

export const DEFAULT_AREA = "wroclaw";

export function initialMapView(hash) {
  const area = AREAS[DEFAULT_AREA];
  return { center: hash.center ?? area.center, zoom: hash.zoom ?? area.zoom };
}

export function areaAt(center) {
  return Object.keys(AREAS).find((key) => {
    const [lon, lat] = AREAS[key].center;
    return Math.abs(center.lng - lon) < 0.001 && Math.abs(center.lat - lat) < 0.001;
  }) ?? "";
}
