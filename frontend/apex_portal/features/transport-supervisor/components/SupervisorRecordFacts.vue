<script setup>
import { ref, watch } from "vue";
import { createResource } from "frappe-ui";
import { dateTimeLabel, statusLabel } from "../../../core/displayLabels.js";
import { __ } from "../../../core/i18n.js";

const props = defineProps({
  doc: { type: Object, required: true },
  fields: { type: Array, default: () => [] },
});

const linkTitle = createResource({
  url: "frappe.client.get_value",
  method: "GET",
  auto: false,
});
const linkLabels = ref({});
let linkLoadVersion = 0;

function displayValue(field) {
  const value = props.doc?.[field.key];
  if (value === null || value === undefined || value === "") {
    return { label: "—", reference: "" };
  }
  if (["starts_on", "ends_on", "generated_through", "trip_date", "planned_start", "planned_end", "pickup_datetime"].includes(field.key)) {
    return { label: dateTimeLabel(value) || value, reference: "" };
  }
  if (field.key === "status") {
    return { label: statusLabel(value), reference: "" };
  }
  if (field.link) {
    return {
      label: props.doc?.[field.labelKey] || linkLabels.value[field.key] || field.link.fallback || __("Linked Record"),
      reference: value,
    };
  }
  return { label: value, reference: "" };
}

// A slow link title must never overwrite the labels of the record opened after it.
async function loadLinkLabels(current) {
  const version = ++linkLoadVersion;
  const next = {};
  if (!current) {
    linkLabels.value = next;
    return;
  }
  for (const field of props.fields) {
    const value = current[field.key];
    if (!field.link || !value) continue;
    try {
      const result = await linkTitle.fetch({
        doctype: field.link.doctype,
        filters: { name: value },
        fieldname: [field.link.fieldname],
      });
      const data = result?.message || result || {};
      next[field.key] = data[field.link.fieldname] || field.link.fallback || __("Linked Record");
    } catch {
      next[field.key] = field.link.fallback || __("Could not fetch the name");
    }
  }
  if (version === linkLoadVersion) linkLabels.value = next;
}

watch(() => props.doc, loadLinkLabels, { immediate: true });
</script>

<template>
  <dl class="feature-details supervisor-detail__facts">
    <template v-for="field in fields" :key="field.key">
      <dt>{{ field.label }}</dt>
      <dd>
        <span dir="auto">{{ displayValue(field).label }}</span>
        <bdi
          v-if="displayValue(field).reference"
          class="record-reference"
          dir="auto"
          translate="no"
        >{{ displayValue(field).reference }}</bdi>
      </dd>
    </template>
  </dl>
</template>
