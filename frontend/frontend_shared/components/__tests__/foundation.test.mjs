// Copyright (c) 2026, AFMCO and contributors
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";

import {
  ActionDock,
  AsyncBoundary,
  DataLedger,
  DecisionStage,
  EvidenceRail,
  MetricRibbon,
  StatusLabel,
  WorkQueue,
} from "@shared/components/index.js";

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: "/", component: { template: "<div />" } }],
});

describe("Quiet Ascent composition", () => {
  it("gives each operational region a stable semantic landmark", () => {
    const queue = mount(WorkQueue, {
      props: { title: "Pending", label: "Pending routes" },
      slots: { default: "<button class='row'>Route 14</button>" },
    });
    expect(queue.element.tagName).toBe("SECTION");
    expect(queue.attributes("aria-label")).toBe("Pending routes");
    expect(queue.find(".work-queue-list .row").exists()).toBe(true);

    const stage = mount(DecisionStage, {
      props: { title: "Route 14", eyebrow: "Awaiting review" },
      slots: { default: "<p class='facts'>Evidence</p>" },
    });
    expect(stage.element.tagName).toBe("ARTICLE");
    expect(stage.find(".decision-stage-body .facts").exists()).toBe(true);

    const evidence = mount(EvidenceRail, {
      props: { title: "Evidence", label: "Plan evidence" },
      slots: { default: "<dl class='facts'></dl>" },
    });
    expect(evidence.element.tagName).toBe("ASIDE");
    expect(evidence.attributes("aria-label")).toBe("Plan evidence");
  });

  it("renders status as text and tone, never colour alone", () => {
    const status = mount(StatusLabel, {
      props: { label: "Delayed", tone: "danger" },
    });
    expect(status.text()).toBe("Delayed");
    expect(status.attributes("data-tone")).toBe("danger");

    const fallback = mount(StatusLabel, {
      props: { label: "Custom", tone: "unknown" },
    });
    expect(fallback.attributes("data-tone")).toBe("neutral");
  });

  it("keeps metrics, ledgers and actions structured without card wrappers", () => {
    const metrics = mount(MetricRibbon, {
      props: {
        metrics: [
          { label: "Pending", value: 7 },
          { label: "On time", value: "94%", tone: "success" },
        ],
      },
    });
    expect(metrics.findAll(".metric-ribbon-item")).toHaveLength(2);
    expect(metrics.findAll("bdi")).toHaveLength(2);

    const ledger = mount(DataLedger, {
      props: { label: "Fleet records" },
      slots: {
        head: "<tr><th>Vehicle</th></tr>",
        default: "<tr><td>ABC 123</td></tr>",
      },
    });
    expect(ledger.find("table").attributes("aria-label")).toBe("Fleet records");
    expect(ledger.find("tbody td").text()).toBe("ABC 123");

    const dock = mount(ActionDock, {
      slots: {
        secondary: "<button class='secondary'>Back</button>",
        primary: "<button class='primary'>Approve</button>",
      },
    });
    expect(dock.find(".action-dock-secondary .secondary").exists()).toBe(true);
    expect(dock.find(".action-dock-primary .primary").exists()).toBe(true);
  });

  it("uses library feedback controls for recoverable async states", async () => {
    const boundary = mount(AsyncBoundary, {
      props: {
        state: "stale",
        title: "Data changed",
        message: "Refresh before deciding.",
        retryLabel: "Refresh",
      },
      global: { plugins: [router] },
    });
    expect(boundary.text()).toContain("Data changed");
    expect(boundary.find("[role='alert']").classes()).toContain("bg-surface-amber-2");
    await boundary.find("button").trigger("click");
    expect(boundary.emitted("retry")).toHaveLength(1);

    await boundary.setProps({ state: "error" });
    expect(boundary.findAll("[role='alert']")).toHaveLength(1);
  });
});
