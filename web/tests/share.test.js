import test from "node:test";
import assert from "node:assert/strict";
import { shareUrl } from "../js/share.js";

const abort = () => Object.assign(new Error("x"), { name: "AbortError" });

test("share ok → shared", async () => {
  let arg;
  const r = await shareUrl("u", "t", { nav: { share: async (a) => { arg = a; } }, notify: () => assert.fail(), promptFn: () => assert.fail() });
  assert.equal(r, "shared");
  assert.deepEqual(arg, { title: "t", url: "u" });
});
test("AbortError → aborted, no notify/copy", async () => {
  const nav = { share: async () => { throw abort(); }, clipboard: { writeText: async () => assert.fail() } };
  assert.equal(await shareUrl("u", "t", { nav, notify: () => assert.fail(), promptFn: () => assert.fail() }), "aborted");
});
test("no share, clipboard → copied + notify", async () => {
  let copied, msg;
  const nav = { clipboard: { writeText: async (t) => { copied = t; } } };
  assert.equal(await shareUrl("u", "t", { nav, notify: (m) => { msg = m; } }), "copied");
  assert.equal(copied, "u");
  assert.equal(msg, "Skopiowano link");
});
test("share fails (non-abort) → falls back to clipboard", async () => {
  const nav = { share: async () => { throw new Error("boom"); }, clipboard: { writeText: async () => {} } };
  assert.equal(await shareUrl("u", "t", { nav, notify: () => {} }), "copied");
});
test("clipboard rejects → prompted", async () => {
  let shown;
  const nav = { clipboard: { writeText: async () => { throw new Error("denied"); } } };
  assert.equal(await shareUrl("u", "t", { nav, notify: () => {}, promptFn: (m, v) => { shown = v; } }), "prompted");
  assert.equal(shown, "u");
});
test("neither → prompted", async () => {
  let shown;
  assert.equal(await shareUrl("u", "t", { nav: {}, notify: () => {}, promptFn: (m, v) => { shown = v; } }), "prompted");
  assert.equal(shown, "u");
});
