import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { PNG } from "pngjs";
import { renderServiceWorker } from "./service-worker-template.js";
import { workerParameters } from "./service-workers.js";

const iconDirectory = path.join(process.cwd(), "public/icons");

/**
 * Largest per-channel distance from a maskable icon's own field colour that still counts as field.
 *
 * A maskable icon's safe zone is a circle of 80 percent diameter, so a launcher mask may crop
 * everything past radius 0.4 * width — 205px of 512 here. The shipped icons carry a decorative
 * rounded panel that reaches radius 247 but sits within 4/255 of the field on every channel, so
 * cropping it changes nothing a person can see; the Apex mark itself stops at radius 143. A scan
 * demanding an exact field match would fail on that invisible panel, and one measuring the
 * inscribed square instead of the circle would pass a mark reaching radius 283 — 78px into the
 * region the mask is free to cut.
 */
const FIELD_TOLERANCE = 8;

/**
 * Reads a PNG's declared pixel dimensions straight from its IHDR chunk.
 *
 * @param {string} file a file name inside public/icons
 * @returns {string} the dimensions in the `WIDTHxHEIGHT` form a manifest `sizes` member uses
 */
const pngDimensions = (file) => {
  const png = readFileSync(path.join(iconDirectory, file));
  return `${png.readUInt32BE(16)}x${png.readUInt32BE(20)}`;
};

describe("portal PWA contract", () => {
  const parameters = () => workerParameters({ assetUrls: [] });

  it("ships two standalone Arabic manifests with canonical scopes", () => {
    for (const [name, route] of [["masar", "/masar/"], ["driver", "/driver/"]]) {
      const manifest = JSON.parse(readFileSync(path.join(process.cwd(), `public/manifests/${name}.webmanifest`), "utf8"));
      expect(manifest.id).toBe(route);
      expect(manifest.start_url).toBe(route);
      expect(manifest.scope).toBe(route);
      expect(manifest.display).toBe("standalone");
      expect(manifest.display_override).toEqual(["standalone"]);
      expect(manifest.lang).toBe("ar");
      expect(manifest.dir).toBe("rtl");
      expect(manifest.theme_color).toBe("#00844E");
      expect(manifest.background_color).toBe("#F8F5EE");
    }
  });

  it("declares every shipped icon once, under a single purpose, at its real size", () => {
    for (const family of ["masar", "driver"]) {
      const manifest = JSON.parse(readFileSync(path.join(process.cwd(), `public/manifests/${family}.webmanifest`), "utf8"));
      const declared = manifest.icons.map((icon) => icon.src.split("/").pop());

      // `purpose` is a set, and a platform asking for one purpose will not accept an icon
      // declared for another: a maskable icon is padded for the mask and reads as a shrunken
      // mark wherever an `any` icon belongs. One purpose per file keeps the two apart, and the
      // Apple touch icon stays out because index.html declares it through <link rel>, not here.
      for (const icon of manifest.icons) {
        expect(icon.purpose.split(" ")).toHaveLength(1);
        expect(["any", "maskable", "monochrome"]).toContain(icon.purpose);
        expect(icon.type).toBe("image/png");
        expect(pngDimensions(icon.src.split("/").pop())).toBe(icon.sizes);
      }
      const sizesFor = (purpose) => manifest.icons
        .filter((icon) => icon.purpose === purpose)
        .map((icon) => icon.sizes)
        .sort();
      expect(sizesFor("any")).toEqual(["192x192", "512x512"]);
      expect(sizesFor("maskable")).toEqual(["512x512"]);

      // An icon shipped but never declared is dead weight, and the surface it was drawn for —
      // the splash screen takes the largest `any` icon — silently upscales a smaller one instead.
      expect(new Set(declared)).toEqual(
        new Set(readdirSync(iconDirectory).filter((name) => name.startsWith(`${family}-icon-`))),
      );
      expect(declared).toHaveLength(new Set(declared).size);
    }
  });

  it("uses distinct exact cache namespaces and network-only navigation", () => {
    const params = parameters();
    expect(params.worker.cacheNamespace).toBe("apex:masar:");
    expect(params.driver.cacheNamespace).toBe("apex:driver:");
    for (const entry of Object.values(params)) {
      const source = renderServiceWorker({ ...entry, build: "deadbeef0000" });
      expect(source).toContain('fetch(request, { cache: "no-store", redirect: "manual" })');
      expect(source).toContain('url.origin !== self.location.origin');
      expect(source).not.toContain('caches.match(request) || fetch(request)');
    }
  });

  it("pre-caches the stylesheet required by the offline document", () => {
    for (const entry of Object.values(parameters())) {
      expect(entry.immutableAssets).toContain("/assets/apex/apex_portal/offline.css");
    }
  });

  it("ships opaque 180 pixel Apple icons", () => {
    for (const entry of ["masar", "driver"]) {
      const png = readFileSync(path.join(process.cwd(), `public/icons/${entry}-apple-touch-icon-180.png`));
      expect(png.readUInt32BE(16)).toBe(180);
      expect(png.readUInt32BE(20)).toBe(180);
      expect(png[25]).toBe(2);
    }
  });

  it("keeps maskable artwork opaque everywhere and its mark inside the safe circle", () => {
    for (const entry of ["masar", "driver"]) {
      const png = PNG.sync.read(readFileSync(path.join(process.cwd(), `public/icons/${entry}-icon-maskable-512.png`)));
      const field = [...png.data.subarray(0, 4)];
      const centre = png.width / 2;
      const safeRadius = 0.4 * png.width;
      let transparent = 0;
      let croppable = 0;

      expect(png.width).toBe(png.height);
      for (let y = 0; y < png.height; y += 1) {
        for (let x = 0; x < png.width; x += 1) {
          const offset = (y * png.width + x) * 4;
          if (png.data[offset + 3] !== 255) transparent += 1;
          if (Math.hypot(x + 0.5 - centre, y + 0.5 - centre) <= safeRadius) continue;
          const inked = [0, 1, 2].some(
            (channel) => Math.abs(png.data[offset + channel] - field[channel]) > FIELD_TOLERANCE,
          );
          if (inked) croppable += 1;
        }
      }

      expect(transparent).toBe(0);
      expect(croppable).toBe(0);
    }
  });

  it("keeps worker and driver notification targets inside their own paths", () => {
    for (const entry of Object.values(parameters())) {
      const source = renderServiceWorker({ ...entry, build: "deadbeef0000" });
      expect(source).toContain('self.addEventListener("push"');
      expect(source).toContain("target.origin === self.location.origin");
      expect(source).toContain("target.pathname.startsWith(NAV_PATH)");
    }
  });
});
