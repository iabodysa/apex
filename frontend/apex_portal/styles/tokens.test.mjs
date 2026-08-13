import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(name, import.meta.url)), "utf8");

describe("Apex portal identity", () => {
  it("uses the approved light palette as semantic tokens", () => {
    const css = read("./tokens.css");
    expect(css).toContain("--c-primary: #00844e");
    expect(css).toContain("--c-canvas: #e9e3d3");
    expect(css).toContain("--c-surface: #f8f5ee");
    expect(css).toContain("--c-ink: #072b1a");
    expect(css).toContain("color-scheme: light");
    expect(css).not.toMatch(/prefers-color-scheme|dark/i);
  });

  it("keeps brand tokens separate from frappe-ui neutral roles", () => {
    const tokens = read("./tokens.css");
    const adapter = read("./frappe-ui-theme.css");
    expect(tokens).not.toMatch(/--(?:surface|ink|outline)-gray-/);
    expect(tokens).not.toContain("--surface-green-");
    expect(adapter).toContain("--surface-green-3: var(--c-primary)");
    expect(adapter).toContain("--ink-green-3: var(--c-primary-hover)");
    expect(adapter).not.toMatch(/--(?:surface|ink|outline)-gray-/);
  });

  it("keeps the offline fallback on the approved type and color tokens", () => {
    const html = read("../public/offline.html");
    const css = read("../public/offline.css");
    expect(html).toContain('/assets/apex/vendor/thmanyah-v1/thmanyah.css');
    expect(css).toContain('font-family: "Thmanyah Sans", sans-serif');
    expect(css).toContain("color: #072b1a");
    expect(css).toContain("color: #47584f");
    expect(css).not.toContain("system-ui");
  });

  it("uses forest for bounded brand fields and primary green for actions and selection", () => {
    const css = read("./foundation.css");
    expect(css).toMatch(/\.operations-shell__rail\s*\{[^}]*background:\s*var\(--surface-2\)/s);
    expect(css).toMatch(/\.operations-shell__nav \.portal-nav-link\[aria-current="page"\]\s*\{[^}]*background:\s*var\(--brand-green\)/s);
    expect(css).toMatch(/\.apex-boot\s*\{[^}]*background:\s*var\(--forest\)/s);
    expect(css).toMatch(/\.mobile-shell__header\s*\{[^}]*background:\s*var\(--forest\)/s);
    expect(css).toMatch(/\.feature-page__heading\s*\{[^}]*background:\s*var\(--forest\)/s);
  });

  it("loads the vendored Thmanyah stylesheet and no remote font", () => {
    const css = `${read("./tokens.css")}\n${read("./foundation.css")}`;
    const html = read("../index.html");
    expect(html).toContain(
      '<link rel="stylesheet" href="/assets/apex/vendor/thmanyah-v1/thmanyah.css" />',
    );
    expect(css).toContain('"Thmanyah Sans"');
    expect(css).not.toMatch(/https?:\/\//);
    expect(css).not.toContain("/assets/apex/vendor/thmanyah-v1/thmanyah.css");
    expect(css).not.toMatch(/Arial|Inter|Roboto/);
  });

  it("sets logical RTL foundations and accessible touch targets", () => {
    const css = read("./foundation.css");
    expect(css).toContain("direction: rtl");
    expect(css).toContain("text-align: start");
    expect(css).toMatch(/min-(?:block-size|height): 44px/);
    expect(css).toContain("env(safe-area-inset-bottom)");
  });

  it("truncates long LTR record references at their visual end", () => {
    const css = read("./foundation.css");
    expect(css).toMatch(/\.record-reference\s*\{[^}]*direction:\s*ltr[^}]*text-align:\s*start[^}]*text-overflow:\s*ellipsis/s);
  });

  it("ships branded waiting and reduced-motion states", () => {
    const css = `${read("./tokens.css")}\n${read("./foundation.css")}`;
    const html = read("../index.html");
    expect(html).toContain('class="apex-boot"');
    expect(html).toContain('/assets/apex/icons/brand/apex-mark-reverse.svg');
    expect(html).toContain("نجهّز أبكس لك");
    expect(css).toContain("--motion-fast: 120ms");
    expect(css).toContain("@media (prefers-reduced-motion: reduce)");
  });

  it("defines every spacing step consumed by portal feature styles", () => {
    const css = read("./tokens.css");
    expect(css).toContain("--sp-5: 20px");
  });

  it("makes each shell own its viewport scroll and keeps the operations rail on iPad", () => {
    const css = read("./foundation.css");
    expect(css).toMatch(/\.mobile-shell\s*\{[^}]*block-size:\s*100dvh[^}]*grid-template-rows:\s*auto minmax\(0, 1fr\) auto/s);
    expect(css).toMatch(/\.mobile-shell__header\s*\{[^}]*position:\s*sticky/s);
    expect(css).toMatch(/\.mobile-shell__main\s*\{[^}]*overflow-y:\s*auto/s);
    expect(css).toMatch(/\.operations-shell__body\s*\{[^}]*block-size:\s*100dvh[^}]*grid-template-rows:\s*auto minmax\(0, 1fr\)/s);
    expect(css).toMatch(/\.operations-shell__main\s*\{[^}]*overflow-y:\s*auto/s);
    expect(css).toContain("@media (max-width: 767px)");
    expect(css).toMatch(/@media \(max-width: 767px\)[\s\S]*?\.operations-shell__rail\s*\{[^}]*min-inline-size:\s*0[^}]*max-inline-size:\s*100%/);
    expect(css).toMatch(/@media \(max-width: 767px\)[\s\S]*?\.operations-shell__nav\s*\{[^}]*min-inline-size:\s*0[^}]*max-inline-size:\s*100%/);
  });

  it("keeps housing room cards vertical when other feature styles are loaded", () => {
    const foundation = read("./foundation.css");
    const housing = read("../features/housing/housing.css");
    expect(foundation).toMatch(/\.feature-card[^}]*\{[^}]*display:\s*grid/s);
    expect(housing).toMatch(/\.room-card\s*\{[^}]*grid-template-columns:\s*1fr[^}]*align-items:\s*stretch/s);
    expect(housing).toMatch(/\.room-card header > div\s*\{[^}]*display:\s*flex[^}]*gap:/s);
  });

  it("keeps all safety checklist decisions readable on the iPad", () => {
    const css = read("../features/housing/housing.css");
    expect(css).toMatch(/\.safety-checklist__decision \.truncate\s*\{[^}]*white-space:\s*normal/s);
    expect(css).toMatch(/@media \(max-width: 1100px\)[\s\S]*?\.safety-task\s*\{[^}]*grid-template-columns:\s*1fr/s);
  });
});
