// Theme-adaptive QR colors that stay SCANNABLE. A QR decoder binarizes on
// luminance, so the only hard requirement is a large light/dark separation with
// the dark modules actually darker than the background. Given a desired
// (dark, light) pair from the active theme, this returns a pair guaranteed to
// clear a high contrast threshold; if the theme pair is too low-contrast or
// inverted (light-on-dark), it clamps toward plain black-on-white.

// Minimum contrast ratio for the QR. Far above the 4.5:1 AA *text* bar — a
// scanner needs a clean luminance split, so we hold a 7:1 floor and clamp below.
const MIN_RATIO = 7;

function clamp8(n) {
  return Math.max(0, Math.min(255, Math.round(n)));
}

// Parse #rgb / #rrggbb / rgb()/rgba() into [r,g,b] (0..255), or null if unknown
// (e.g. color-mix() — the caller falls back to black-on-white).
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

// sRGB relative luminance per WCAG 2.x.
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

// Resolve the dark-module + light-background colors for the active theme.
// Returns { dark, light } as hex strings. Guarantees: dark is the darker of the
// two, and the pair clears MIN_RATIO — else falls back to black-on-white.
export function qrColors(darkInput, lightInput) {
  const dark = parseColor(darkInput);
  const light = parseColor(lightInput);
  if (!dark || !light) return { dark: "#000000", light: "#ffffff" };

  // The "dark" module must actually be darker than the background, or a scanner
  // reads the code inverted. If the theme inverts it (light ink on a dark
  // surface — e.g. the dark theme), don't try to honor it; use black-on-white.
  if (luminance(dark) >= luminance(light)) return { dark: "#000000", light: "#ffffff" };

  // Theme pair is correctly oriented but may be too soft; require the floor.
  // If it falls short, deepen the dark toward black and lift the light toward
  // white until the ratio clears (keeps the theme HUE while restoring contrast).
  let d = dark.slice();
  let l = light.slice();
  let guard = 0;
  while (contrastRatio(d, l) < MIN_RATIO && guard++ < 24) {
    d = d.map((c, i) => clamp8(c + (BLACK[i] - c) * 0.25));
    l = l.map((c, i) => clamp8(c + (WHITE[i] - c) * 0.25));
  }
  // Even after deepening it can't reach the floor (rare): be safe.
  if (contrastRatio(d, l) < MIN_RATIO) return { dark: "#000000", light: "#ffffff" };
  return { dark: toHex(d), light: toHex(l) };
}

export { MIN_RATIO, contrastRatio };
