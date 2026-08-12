import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { safetyRoutes } from "./routes.js";

describe("safety feature contract", () => {
  it("ships the round list and review routes", () => {
    expect(safetyRoutes.map((route) => route.path)).toEqual(["/rounds", "/rounds/:name"]);
  });

  it("loads every safety page module", async () => {
    const pages = await Promise.all(safetyRoutes.map((route) => route.component()));
    expect(pages).toHaveLength(safetyRoutes.length);
    expect(pages.every((page) => page.default)).toBe(true);
  });

  it("uses frappe-ui FileUploader and never stores Base64 into Attach fields", () => {
    const source = readFileSync(
      join(process.cwd(), "features/safety/components/SafetyTaskRow.vue"),
      "utf8",
    );
    expect(source).toContain("FileUploader");
    expect(source).toContain("file_url");
    expect(source).not.toMatch(/base64|readAsDataURL/i);
  });

  it("shows the review action only to a server-granted checker", () => {
    const source = readFileSync(
      join(process.cwd(), "features/safety/pages/SafetyRoundReviewPage.vue"),
      "utf8",
    );
    expect(source).toContain('includes("safety_check")');
    expect(source).toContain('v-if="canReview');
    expect(source).toContain("row.evidence_photo");
    expect(source).toContain("row.notes");
    expect(source).toContain("row.linked_maintenance_request");
  });
});
