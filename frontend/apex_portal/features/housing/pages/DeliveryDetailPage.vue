<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { Button, ErrorMessage, FormControl, LoadingIndicator, createResource, toast } from "frappe-ui";
import { statusLabel } from "../../../core/displayLabels.js";

const route = useRoute();
const code = ref("");
const error = ref("");
const capabilities = globalThis.window?.apex_portal?.capabilities || [];
const delivery = createResource({
  url: "frappe.client.get",
  makeParams: () => ({ doctype: "Facility Asset Delivery", name: route.params.name }),
});
const exit1 = createResource({ url: "apex.habitat.api.facility_asset_delivery.pass_exit_1" });
const exit3 = createResource({ url: "apex.habitat.api.facility_asset_delivery.pass_exit_3" });
const receipt = createResource({ url: "apex.habitat.api.facility_asset_delivery.confirm_receipt" });
const busy = computed(() => exit1.loading || exit3.loading || receipt.loading);

onMounted(() => delivery.fetch());
async function run(resource, params, message) {
  error.value = "";
  try {
    await resource.submit(params);
    toast.create({ type: "success", message });
    code.value = "";
    await delivery.fetch();
  } catch (exception) {
    error.value = exception.message || "تعذر تنفيذ الإجراء.";
  }
}
</script>

<template>
  <section class="feature-page">
    <h2>تفاصيل تسليم الأصل</h2>
    <LoadingIndicator v-if="delivery.loading" aria-label="جارٍ التحميل" />
    <ErrorMessage v-else-if="delivery.error" message="تعذر تحميل عملية التسليم." />
    <template v-else-if="delivery.data">
      <article class="feature-card">
        <strong dir="auto">{{ delivery.data.facility_asset }}</strong>
        <span>{{ delivery.data.from_building }} ← {{ delivery.data.to_building }}</span>
        <small>{{ statusLabel(delivery.data.status) }}</small>
      </article>
      <div class="feature-actions">
        <Button
          v-if="capabilities.includes('clear_exit_1')"
          variant="solid"
          :loading="exit1.loading"
          :disabled="busy || delivery.data.exit1_security_cleared"
          @click="run(exit1, { delivery: delivery.data.name }, 'تم اعتماد بوابة التسليم')"
        >اعتماد بوابة التسليم</Button>
        <Button
          v-if="capabilities.includes('clear_exit_3')"
          variant="solid"
          :loading="exit3.loading"
          :disabled="busy || delivery.data.exit3_receiving_cleared"
          @click="run(exit3, { delivery: delivery.data.name }, 'تم اعتماد الاستلام')"
        >اعتماد الاستلام</Button>
      </div>
      <form v-if="capabilities.includes('confirm_delivery_receipt') && delivery.data.status === 'Released'" class="feature-form" @submit.prevent="run(receipt, { delivery: delivery.data.name, code }, 'تم تأكيد الاستلام')">
        <FormControl v-model="code" label="رمز الاستلام" inputmode="numeric" required />
        <Button type="submit" variant="solid" :loading="receipt.loading" :disabled="code.length !== 6">تأكيد الاستلام</Button>
      </form>
      <ErrorMessage v-if="error" :message="error" />
    </template>
  </section>
</template>
