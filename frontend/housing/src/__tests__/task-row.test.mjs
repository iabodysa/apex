// @vitest-environment jsdom
// Copyright (c) 2026, afmcoltd
import { describe, expect, it, vi } from "vitest";
import { shallowMount } from "@vue/test-utils";

vi.mock("frappe-ui", () => ({
  Button: { name: "Button", emits: ["click"], template: "<button @click='$emit(\"click\")'><slot /></button>" },
  FileUploader: { name: "FileUploader", template: "<div><slot /></div>" },
  FormControl: { name: "FormControl", template: "<input />" },
}));

import { Button, FormControl } from "frappe-ui";

import TaskRow from "../components/TaskRow.vue";

describe("safety task controls", () => {
  it("uses frappe-ui for every generic action and note field", async () => {
    const wrapper = shallowMount(TaskRow, {
      props: { task: { name: "Door", task_title: "Door" } },
    });

    expect(wrapper.findAllComponents(Button)).toHaveLength(4);
    await wrapper.findAllComponents(Button)[3].trigger("click");
    expect(wrapper.findComponent(FormControl).exists()).toBe(true);
    expect(wrapper.find("textarea").exists()).toBe(false);
  });
});
