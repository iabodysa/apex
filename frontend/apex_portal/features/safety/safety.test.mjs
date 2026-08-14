import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { safetyRoutes } from "./routes.js";
import SafetyTaskRow from "./components/SafetyTaskRow.vue";

describe("safety feature contract", () => {
  it("groups the mobile safety destination with maintenance operations", () => {
    const route = safetyRoutes.find((candidate) => candidate.path === "/rounds");
    expect(route.meta.group).toBe("الصيانة والسلامة");
  });

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

  it("waits for an explicit visible checklist decision", async () => {
    const wrapper = mount(SafetyTaskRow, {
      props: {
        task: {
          name: "STC-0001",
          task_title: "فحص طفايات الحريق",
          evidence_required: 1,
        },
        cadence: "Daily",
      },
    });

    expect(wrapper.emitted("change")).toBeUndefined();
    expect(wrapper.find("select").exists()).toBe(false);
    expect(wrapper.findAll(".safety-checklist__decision")).toHaveLength(3);
    expect(wrapper.text()).toContain("سليم");
    expect(wrapper.text()).toContain("يحتاج معالجة");
    expect(wrapper.text()).toContain("لم يُفحص");

    await wrapper.get(".safety-checklist__decision--good").trigger("click");
    expect(wrapper.emitted("change")?.at(-1)?.[0]).toMatchObject({
      task: "STC-0001",
      cadence: "Daily",
      execution_status: "Good",
    });

    await wrapper.get(".safety-checklist__decision--poor").trigger("click");
    expect(wrapper.emitted("change")?.at(-1)?.[0].execution_status).toBe("Poor");
    expect(wrapper.find(".safety-checklist__evidence").exists()).toBe(true);

    await wrapper.get(".safety-checklist__decision--not-done").trigger("click");
    expect(wrapper.emitted("change")?.at(-1)?.[0].execution_status).toBe("Not Done");
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
    expect(source).toContain('"task.task_title as task_title"');
    expect(source).toContain("row.task_title");
  });
});
