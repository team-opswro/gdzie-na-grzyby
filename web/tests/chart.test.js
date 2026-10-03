import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { chartData, trend, DOW, renderChart } from "../js/chart.js";

const load = (n) => JSON.parse(fs.readFileSync(new URL(`../../tests/fixtures/${n}`, import.meta.url), "utf8"));
const P = load("pogoda.json");
const V1 = load("pogoda_v1.json");
const CELL = "506_178";

// Syntetyczna pogoda: wyniki = h * w, h = 100 → score = round(100 * w).
function synth(ws) {
  const days = ws.map((_, i) => `2026-10-${String(2 + i).padStart(2, "0")}`);
  const z = ws.map(() => 0);
  return { days, cells: { c: { borowik: { w: ws, rain: z, temp: z, season: z } } } };
}

test("DOW", () => assert.deepEqual(DOW, ["nd", "pn", "wt", "śr", "czw", "pt", "sob"]));

test("chartData skips past days: 7 items, first idx 1", () => {
  const d = chartData(P, CELL, "borowik", 80, P.days[1]);
  assert.equal(d.length, 7);
  assert.equal(d[0].idx, 1);
  assert.equal(d[0].date, P.days[1]);
  assert.equal(d[0].score, Math.round(80 * P.cells[CELL].borowik.w[1]));
  assert.equal(typeof d[0].cls, "number");
});
test("chartData caps at 7 when all 8 days are available", () =>
  assert.equal(chartData(P, CELL, "borowik", 80, P.days[0]).length, 7));
test("chartData missing w → null score and cls", () => {
  const p = synth([0.5, null, 0.5]);
  const d = chartData(p, "c", "borowik", 100, "2026-10-02");
  assert.deepEqual(d[1], { date: "2026-10-03", idx: 1, score: null, cls: null });
});
test("chartData missing cell → nulls, no throw", () => {
  const d = chartData(P, "999_999", "borowik", 80, P.days[1]);
  assert.ok(d.every((x) => x.score === null && x.cls === null));
});

test("trend uses yesterday (idx 0) for dayIdx 1", () => {
  const t = trend(P, CELL, "borowik", 80, 1);
  const s = (i) => Math.round(80 * P.cells[CELL].borowik.w[i]);
  assert.equal(t.delta, s(1) - s(0));
});
test("trend dayIdx 0 → dir null", () => assert.equal(trend(P, CELL, "borowik", 80, 0).dir, null));
test("trend thresholds ±5", () => {
  assert.deepEqual(trend(synth([0.5, 0.55]), "c", "borowik", 100, 1).dir, "up");
  assert.equal(trend(synth([0.5, 0.54]), "c", "borowik", 100, 1).dir, "flat");
  assert.equal(trend(synth([0.5, 0.54]), "c", "borowik", 100, 1).delta, 4);
  assert.equal(trend(synth([0.5, 0.45]), "c", "borowik", 100, 1).dir, "down");
  assert.equal(trend(synth([0.5, 0.45]), "c", "borowik", 100, 1).delta, -5);
});
test("trend null when a score is missing", () => {
  const t = trend(synth([null, 0.5]), "c", "borowik", 100, 1);
  assert.equal(t.dir, null);
  assert.equal(t.delta, null);
});
test("peak only when later day >= current + 5; ties earliest", () => {
  const t = trend(synth([0.5, 0.5, 0.55, 0.6, 0.6]), "c", "borowik", 100, 1);
  assert.deepEqual(t.peak, { idx: 3, date: "2026-10-05", score: 60 });
  assert.equal(trend(synth([0.5, 0.5, 0.54, 0.5]), "c", "borowik", 100, 1).peak, null);
  assert.equal(trend(synth([0.5, 0.5, 0.55]), "c", "borowik", 100, 1).peak.idx, 2);
});
test("v1 fixture: trend(…, 0) → dir null, no throw", () => {
  const cell = Object.keys(V1.cells)[0];
  const t = trend(V1, cell, "borowik", 80, 0);
  assert.equal(t.dir, null);
});
test("v1 fixture: chartData works", () => {
  const cell = Object.keys(V1.cells)[0];
  assert.ok(chartData(V1, cell, "borowik", 80, V1.days[0]).length > 0);
});

// Minimalny stub DOM tylko na czas testu renderChart.
function stubDom() {
  const mk = (ns, tag) => ({
    ns, tag, attrs: {}, children: [], listeners: {}, textContent: "",
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k]; },
    append(...c) { this.children.push(...c); },
    appendChild(c) { this.children.push(c); return c; },
    addEventListener(t, f) { (this.listeners[t] ||= []).push(f); },
  });
  globalThis.document = { createElementNS: mk };
}
const walk = (n, f) => { f(n); n.children.forEach((c) => walk(c, f)); };

test("renderChart: bars with a11y attrs, click and keyboard select", () => {
  stubDom();
  try {
    const data = chartData(P, CELL, "borowik", 80, P.days[1]);
    const picked = [];
    const svg = renderChart(data, data[2].idx, (i) => picked.push(i));
    assert.equal(svg.tag, "svg");
    assert.equal(svg.getAttribute("viewBox"), "0 0 252 90");
    const bars = [];
    walk(svg, (n) => n.attrs.role === "button" && bars.push(n));
    assert.equal(bars.length, 7);
    assert.equal(bars[0].attrs.tabindex, "0");
    assert.match(bars[0].attrs["aria-label"], /^\S+\. \d+ \S+: \d+$/);
    bars[1].listeners.click[0]({});
    assert.deepEqual(picked, [data[1].idx]);
    let prevented = 0;
    const ev = (key) => ({ key, preventDefault() { prevented++; } });
    bars[3].listeners.keydown[0](ev("Enter"));
    bars[4].listeners.keydown[0](ev(" "));
    bars[5].listeners.keydown[0](ev("a"));
    assert.deepEqual(picked, [data[1].idx, data[3].idx, data[4].idx]);
    assert.equal(prevented, 2);
  } finally {
    delete globalThis.document;
  }
});
test("renderChart: no data → outline only, label 'brak danych'", () => {
  stubDom();
  try {
    const svg = renderChart([{ date: "2026-10-03", idx: 1, score: null, cls: null }], 1, () => {});
    const bars = [];
    walk(svg, (n) => n.attrs.role === "button" && bars.push(n));
    assert.match(bars[0].attrs["aria-label"], /brak danych/);
  } finally {
    delete globalThis.document;
  }
});
