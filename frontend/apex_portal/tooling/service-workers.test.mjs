import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import { renderServiceWorker } from "./service-worker-template.js";
import { workerParameters } from "./service-workers.js";

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
      expect(manifest.icons.map((icon) => icon.purpose)).toEqual(["any maskable", "any maskable"]);
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

  it("keeps worker and driver notification targets inside their own paths", () => {
    for (const entry of Object.values(parameters())) {
      const source = renderServiceWorker({ ...entry, build: "deadbeef0000" });
      expect(source).toContain('self.addEventListener("push"');
      expect(source).toContain("target.origin === self.location.origin");
      expect(source).toContain("target.pathname.startsWith(NAV_PATH)");
    }
  });
});
