// Copyright (c) 2026, afmcoltd

const MIN_RATIO = 7;

function clamp8(n) {
  return Math.max(0, Math.min(255, Math.round(n)));
}

export function parseColor(str) {
  if (!str) return null;
  const s = String(str).trim();
  let m = s.match(/^#([0-9a-f]{3})$/i);
  if (m) {
    const h = m[1];
    return [h[0], h[1], h[2]].map((c) => parseInt(c + c, 16));
  }
  m = s.match(/^#([0-9a-f]{6})$/i);
  if (m) {
    const h = m[1];
    return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  }
  m = s.match(/^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i);
  if (m) return [clamp8(+m[1]), clamp8(+m[2]), clamp8(+m[3])];
  return null;
}

function luminance([r, g, b]) {
  const lin = (c) => {
    const x = c / 255;
    return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrastRatio(a, b) {
  const la = luminance(a);
  const lb = luminance(b);
  const hi = Math.max(la, lb);
  const lo = Math.min(la, lb);
  return (hi + 0.05) / (lo + 0.05);
}

function toHex([r, g, b]) {
  return "#" + [r, g, b].map((c) => clamp8(c).toString(16).padStart(2, "0")).join("");
}

const BLACK = [0, 0, 0];
const WHITE = [255, 255, 255];

export function qrColors(darkInput, lightInput) {
  const dark = parseColor(darkInput);
  const light = parseColor(lightInput);
  if (!dark || !light) return { dark: "#000000", light: "#ffffff" };

  if (luminance(dark) >= luminance(light)) return { dark: "#000000", light: "#ffffff" };

  let d = dark.slice();
  let l = light.slice();
  let guard = 0;
  while (contrastRatio(d, l) < MIN_RATIO && guard++ < 24) {
    d = d.map((c, i) => clamp8(c + (BLACK[i] - c) * 0.25));
    l = l.map((c, i) => clamp8(c + (WHITE[i] - c) * 0.25));
  }
  if (contrastRatio(d, l) < MIN_RATIO) return { dark: "#000000", light: "#ffffff" };
  return { dark: toHex(d), light: toHex(l) };
}

export { MIN_RATIO, contrastRatio };
