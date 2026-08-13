import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(name, import.meta.url)), "utf8");

describe("Apex portal identity", () => {
  it("uses the approved light palette as semantic tokens", () => {
    const css = read("./tokens.css");
    expect(css).toContain("--brand-green: #00844e");
    expect(css).toContain("--canvas: #e9e3d3");
    expect(css).toContain("--surface: #f8f5ee");
    expect(css).toContain("--ink: #072b1a");
    expect(css).toContain("color-scheme: light");
    expect(css).not.toMatch(/prefers-color-scheme|dark/i);
  });

  it("passes Apex semantic colors into frappe-ui components", () => {
    const css = `${read("./tokens.css")}\n${read("../features/housing/housing.css")}`;
    expect(css).toContain("--surface-gray-7: var(--brand-green)");
    expect(css).toContain("--surface-gray-6: var(--brand-green-hover)");
    expect(css).toContain("--surface-gray-5: var(--brand-green-active)");
    expect(css).toContain("--ink-gray-8: var(--ink)");
    expect(css).toContain("--outline-gray-2: var(--border)");
  });

  it("uses the approved brand field for operations navigation", () => {
    const css = read("./foundation.css");
    expect(css).toMatch(/\.operations-shell__rail\s*\{[^}]*background:\s*var\(--forest\)/s);
    expect(css).toMatch(/\.operations-shell__nav \.portal-nav-link\[aria-current="page"\]\s*\{[^}]*background:\s*var\(--brand-green\)/s);
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

  it("makes each shell own its viewport scroll and switches operations before iPad portrait", () => {
    const css = read("./foundation.css");
    expect(css).toMatch(/\.mobile-shell\s*\{[^}]*block-size:\s*100dvh[^}]*grid-template-rows:\s*auto minmax\(0, 1fr\) auto/s);
    expect(css).toMatch(/\.mobile-shell__header\s*\{[^}]*position:\s*sticky/s);
    expect(css).toMatch(/\.mobile-shell__main\s*\{[^}]*overflow-y:\s*auto/s);
    expect(css).toMatch(/\.operations-shell__body\s*\{[^}]*block-size:\s*100dvh[^}]*grid-template-rows:\s*auto minmax\(0, 1fr\)/s);
    expect(css).toMatch(/\.operations-shell__main\s*\{[^}]*overflow-y:\s*auto/s);
    expect(css).toContain("@media (max-width: 1023px)");
    expect(css).toMatch(/@media \(max-width: 1023px\)[\s\S]*?\.operations-shell__rail\s*\{[^}]*min-inline-size:\s*0[^}]*max-inline-size:\s*100%/);
    expect(css).toMatch(/@media \(max-width: 1023px\)[\s\S]*?\.operations-shell__nav\s*\{[^}]*min-inline-size:\s*0[^}]*max-inline-size:\s*100%/);
  });
});
