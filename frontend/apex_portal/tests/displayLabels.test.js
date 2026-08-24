import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it } from "vitest";

import { resetMessages } from "../core/i18n.js";
import { dateTimeLabel, floorLabel, optionLabel, periodLabel, portalTimeZone, remainingSeconds, statusLabel } from "../core/displayLabels.js";

const catalogue = readCatalogue();

function readCatalogue() {
  const path = fileURLToPath(new URL("../../../apex/translations/ar.csv", import.meta.url));
  const rows = {};
  for (const line of readFileSync(path, "utf8").split("\n")) {
    const match = line.match(/^(?:"((?:[^"]|"")*)"|([^",]*)),(?:"((?:[^"]|"")*)"|(.*))$/);
    if (!match) continue;
    const key = (match[1] ?? match[2] ?? "").replace(/""/g, '"');
    const value = (match[3] ?? match[4] ?? "").replace(/""/g, '"');
    if (key) rows[key] = value;
  }
  return rows;
}

function serve(messages, timezone) {
  globalThis.document = {
    documentElement: { lang: "ar", dataset: timezone ? { timezone } : {} },
    getElementById: (id) =>
      id === "apex-portal-messages"
        ? { getAttribute: () => "application/json", textContent: JSON.stringify(messages) }
        : null,
  };
  resetMessages();
}

describe("portal display labels", () => {
  beforeEach(() => {
    serve(catalogue);
  });

  it("reads a status through the catalogue the source string keys", () => {
    expect(catalogue.Approved).toBeTruthy();
    expect(catalogue.Approved).not.toBe("Approved");
    expect(statusLabel("Approved")).toBe(catalogue.Approved);
  });

  it("renders a server state code as the sentence a rider reads", () => {
    const source = "The bus is at your stop";
    expect(catalogue[source]).toBeTruthy();
    expect(optionLabel("at_stop")).toBe(catalogue[source]);
  });

  it("keeps a value the catalogue does not carry", () => {
    expect(optionLabel("Hilux 2019")).toBe("Hilux 2019");
    expect(optionLabel("")).toBe("");
  });

  it("falls back to the new status when a record carries none", () => {
    expect(statusLabel("")).toBe(catalogue.New);
  });

  it("places a number inside the translated sentence", () => {
    expect(floorLabel("Floor 3")).toBe(catalogue["Floor {0}"].replace("{0}", "3"));
    expect(periodLabel({ kind: "year", year: 2026 })).toBe(catalogue["Year {0}"].replace("{0}", "2026"));
    expect(periodLabel({ kind: "day" })).toBe(catalogue.Today);
  });

  it("reads a server time as the wall clock of the zone the page declares", () => {
    const noon = Date.UTC(2026, 7, 24, 12, 0, 0);
    serve(catalogue, "UTC");
    expect(portalTimeZone()).toBe("UTC");
    const shown = dateTimeLabel("2026-08-24 21:00:00");
    expect(remainingSeconds("2026-08-24 21:00:00", 0, noon)).toBe(32400);
    serve(catalogue, "Asia/Riyadh");
    expect(dateTimeLabel("2026-08-24 21:00:00")).toBe(shown);
    expect(remainingSeconds("2026-08-24 21:00:00", 0, noon)).toBe(21600);
  });

  it("serves English when no catalogue reaches the page", () => {
    serve({});
    expect(statusLabel("Approved")).toBe("Approved");
    expect(optionLabel("en_route")).toBe("The bus is on its way");
  });
});
