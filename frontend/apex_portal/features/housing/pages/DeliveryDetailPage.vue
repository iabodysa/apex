<script setup>
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { Badge, Button, ErrorMessage, FormControl, LoadingIndicator, createDocumentResource, createResource, toast } from "frappe-ui";
import { statusLabel, statusTheme } from "../../../core/displayLabels.js";

const route = useRoute();
const code = ref("");
const error = ref("");
const capabilities = globalThis.window?.apex_portal?.capabilities || [];
const delivery = createDocumentResource({
  doctype: "Facility Asset Delivery",
  name: route.params.name,
});
const exit1 = createResource({ url: "apex.habitat.api.facility_asset_delivery.pass_exit_1" });
const exit3 = createResource({ url: "apex.habitat.api.facility_asset_delivery.pass_exit_3" });
const receipt = createResource({
  url: "apex.habitat.api.facility_asset_delivery.confirm_receipt",
});
const assetTitle = createResource({ url: "frappe.client.get_value", method: "GET", auto: false });
const busy = computed(() => exit1.loading || exit3.loading || receipt.loading);
const assetName = computed(() => assetTitle.data?.asset_name || "أصل سكني");

watch(
  () => delivery.doc?.facility_asset,
  (name) => name && assetTitle.fetch({
    doctype: "Facility Asset",
    filters: { name },
    fieldname: ["asset_name"],
  }),
  { immediate: true },
);

async function run(resource, params, message) {
  error.value = "";
  try {
    await resource.submit(params);
    toast.create({ type: "success", message });
    code.value = "";
    await delivery.reload();
  } catch (exception) {
    error.value = exception.message || "تعذر تنفيذ الإجراء.";
  }
}
</script>

<template>
  <section class="feature-page">
    <h2>تفاصيل تسليم الأصل</h2>
    <LoadingIndicator v-if="delivery.get.loading" aria-label="جارٍ التحميل" />
    <ErrorMessage v-else-if="delivery.get.error" message="تعذر تحميل عملية التسليم." />
    <template v-else-if="delivery.doc">
      <article class="feature-card">
        <div class="record-identity">
          <strong dir="auto">{{ assetName }}</strong>
          <bdi class="record-reference" dir="auto" translate="no">{{ delivery.doc.asset_serial_number || delivery.doc.facility_asset }}</bdi>
        </div>
        <span>{{ delivery.doc.from_building }} ← {{ delivery.doc.to_building }}</span>
        <Badge :theme="statusTheme(delivery.doc.status)" :label="statusLabel(delivery.doc.status)" />
      </article>
      <div class="feature-actions">
        <Button v-if="capabilities.includes('clear_exit_1')" theme="green" variant="solid" :loading="exit1.loading" :disabled="busy || delivery.doc.exit1_security_cleared" @click="run(exit1, { delivery: delivery.doc.name }, 'تم اعتماد بوابة التسليم')">اعتماد بوابة التسليم</Button>
        <Button v-if="capabilities.includes('clear_exit_3')" theme="green" variant="solid" :loading="exit3.loading" :disabled="busy || delivery.doc.exit3_receiving_cleared" @click="run(exit3, { delivery: delivery.doc.name }, 'تم اعتماد الاستلام')">اعتماد الاستلام</Button>
      </div>
      <form v-if="capabilities.includes('confirm_delivery_receipt') && delivery.doc.status === 'Released'" class="feature-form" @submit.prevent="run(receipt, { delivery: delivery.doc.name, code }, 'تم تأكيد الاستلام')">
        <FormControl v-model="code" label="رمز الاستلام" inputmode="numeric" required />
        <Button type="submit" theme="green" variant="solid" :loading="receipt.loading" :disabled="code.length !== 6">تأكيد الاستلام</Button>
      </form>
      <ErrorMessage v-if="error" :message="error" />
    </template>
  </section>
</template>
