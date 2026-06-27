// Plain-node unit test for src/qrColor.js (no framework). Run: node qrColor.test.mjs
// Locks the themed-QR contrast invariants that keep the code SCANNABLE: the
// resolved pair always clears the contrast floor, dark stays darker than light,
// and an inverted (light-ink-on-dark) theme clamps to black-on-white.
// (The full round-trip jsQR decode oracle lives in a scratch harness — vendoring
// jsQR as a repo dep is unwarranted; this guards the new color math.)
import { qrColors, contrastRatio, MIN_RATIO, parseColor } from "./src/qrColor.js";

function lum([r, g, b]) {
  const lin = (c) => {
    const x = c / 255;
    return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

// (ink, surface) pairs for the shipped themes + edge cases.
const cases = [
  ["afmco", "#072b1a", "#f8f5ee", false],
  ["frappe", "#1f272e", "#ffffff", false],
  ["dark", "#e7efe9", "#15211b", true], // inverted → must clamp to b/w
  ["soft", "#777777", "#cccccc", false], // low contrast → must deepen to floor
  ["rgb-pair", "rgb(20,40,30)", "rgb(248,245,238)", false],
  ["unparseable", "color-mix(in srgb, red, blue)", "#fff", true], // → b/w fallback
];

let failed = 0;
function check(cond, msg) {
  if (!cond) {
    failed++;
    console.error("FAIL  " + msg);
  }
}

for (const [name, ink, surface, expectBW] of cases) {
  const { dark, light } = qrColors(ink, surface);
  const d = parseColor(dark);
  const l = parseColor(light);
  const ratio = contrastRatio(d, l);

  check(ratio >= MIN_RATIO - 0.001, `${name}: ratio ${ratio.toFixed(2)} below floor ${MIN_RATIO}`);
  check(lum(d) < lum(l), `${name}: dark module not darker than light bg`);
  if (expectBW) {
    check(dark === "#000000" && light === "#ffffff", `${name}: expected black-on-white clamp, got ${dark}/${light}`);
  }
}

// A non-inverted theme should preserve its hue (not silently flip to pure b/w).
const afmco = qrColors("#072b1a", "#f8f5ee");
check(afmco.dark !== "#000000", "afmco dark should keep the theme ink, not clamp to black");

if (failed) {
  console.error(`${failed} qrColor invariant check(s) failed`);
  process.exit(1);
}
console.log(`qrColor invariants: ${cases.length} theme pairs ok (contrast >= ${MIN_RATIO}, dark<light, inverted→b/w)`);
