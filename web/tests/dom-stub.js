// Minimalny atrapa DOM do testów renderujących w node.
function mk(tag) {
  return {
    tag, children: [], style: {}, attrs: {}, className: "", textContent: "",
    append(...c) { this.children.push(...c); },
    appendChild(c) { this.children.push(c); return c; },
    setAttribute(k, v) { this.attrs[k] = v; },
    addEventListener() {},
  };
}
export function installDom() {
  globalThis.document = { createElement: mk, createElementNS: (_n, t) => mk(t) };
}
export function walk(node, fn) {
  if (typeof node === "string") return;
  fn(node);
  node.children?.forEach((c) => walk(c, fn));
}
export const texts = (node) => { const out = []; walk(node, (n) => { if (n.textContent) out.push(n.textContent); }); return out; };
