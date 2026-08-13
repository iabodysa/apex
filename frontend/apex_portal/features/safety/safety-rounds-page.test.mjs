import { beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import SafetyRoundsPage from "./pages/SafetyRoundsPage.vue";
import { selectBuilding } from "../housing/building.js";

const { dueResource, submitResource } = vi.hoisted(() => ({
  dueResource: {
    data: {
      due: [{
        cadence: "Daily",
        period: { kind: "day" },
        tasks: [
          { name: "STC-0001", task_title: "فحص الطفايات" },
          { name: "STC-0002", task_title: "فحص مخارج الطوارئ" },
        ],
      }],
      awaiting: [],
    },
    loading: false,
    error: null,
    fetch: vi.fn(),
  },
  submitResource: { loading: false, submit: vi.fn() },
}));

vi.mock("frappe-ui", () => ({
  Button: {
    props: ["disabled", "loading"],
    template: "<button :disabled='disabled'><slot /></button>",
  },
  ErrorMessage: { props: ["message"], template: "<p>{{ message }}</p>" },
  LoadingIndicator: { template: "<span />" },
  createResource: ({ url }) => url.endsWith("submit_due_rounds") ? submitResource : dueResource,
  toast: { create: vi.fn() },
}));

const taskStub = {
  props: ["task"],
  emits: ["change"],
  template: `
    <button
      class="test-check-task"
      @click="$emit('change', {
        task: task.name,
        cadence: task.cadence,
        execution_status: 'Good',
        notes: '',
        evidence_photo: '',
      })"
    >{{ task.task_title }}</button>
  `,
};

describe("safety round checklist", () => {
  beforeEach(() => {
    selectBuilding("BLD-0001");
    submitResource.submit.mockReset();
  });

  it("keeps save disabled until every due task has an explicit decision", async () => {
    const wrapper = mount(SafetyRoundsPage, {
      global: {
        stubs: {
          BuildingPicker: true,
          SafetyTaskRow: taskStub,
        },
      },
    });
    await nextTick();

    const save = wrapper.get(".safety-checklist__save");
    expect(save.attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("0 من 2");

    const tasks = wrapper.findAll(".test-check-task");
    await tasks[0].trigger("click");
    expect(save.attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("1 من 2");

    await tasks[1].trigger("click");
    expect(save.attributes("disabled")).toBeUndefined();
    expect(wrapper.text()).toContain("اكتملت بنود الجولة");
  });
});
