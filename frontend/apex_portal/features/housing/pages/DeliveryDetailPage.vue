<script setup>
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { Badge, Button, ErrorMessage, FormControl, createDocumentResource, createResource, toast } from "frappe-ui";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import { statusLabel, statusTheme } from "../../../core/displayLabels.js";
import { safeErrorMessage } from "../../../core/errorMessage.js";
import { __ } from "../../../core/i18n.js";

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
const assetName = computed(() => assetTitle.data?.asset_name || __("Housing Asset"));
// A clearance button greys once its gate is already passed and again while a sibling call is in
// flight. The two look identical, and only one of them is worth waiting for.
const clearanceReason = (cleared, done) => {
  if (cleared) return done;
  return busy.value ? __("Another action is already running on this record.") : "";
};
const exit1Reason = computed(() => clearanceReason(delivery.doc?.exit1_security_cleared, __("The delivery gate was already cleared.")));
const exit3Reason = computed(() => clearanceReason(delivery.doc?.exit3_receiving_cleared, __("The receiving was already confirmed.")));

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
    error.value = safeErrorMessage(exception, __("Could not complete the action."));
  }
}
</script>

<template>
  <section class="feature-page">
    <h2>{{ __("Asset Handover Details") }}</h2>
    <PortalSkeleton v-if="delivery.get.loading" :rows="3" :label="__('Loading...')" />
    <ErrorMessage v-else-if="delivery.get.error" :message="__('Could not load the delivery.')" />
    <template v-else-if="delivery.doc">
      <article class="feature-card">
        <div class="record-identity">
          <strong dir="auto">{{ assetName }}</strong>
          <bdi class="record-reference" dir="auto" translate="no">{{ delivery.doc.asset_serial_number || delivery.doc.facility_asset }}</bdi>
        </div>
        <span><bdi dir="auto">{{ delivery.doc.from_building }}</bdi> ← <bdi dir="auto">{{ delivery.doc.to_building }}</bdi></span>
        <Badge :theme="statusTheme(delivery.doc.status)" :label="statusLabel(delivery.doc.status)" />
      </article>
      <div class="feature-actions">
        <Button v-if="capabilities.includes('clear_exit_1')" theme="green" variant="solid" :loading="exit1.loading" :disabled="busy || delivery.doc.exit1_security_cleared" @click="run(exit1, { delivery: delivery.doc.name }, __('The delivery gate was cleared'))">{{ __("Clear Delivery Gate") }}</Button>
        <Button v-if="capabilities.includes('clear_exit_3')" theme="green" variant="solid" :loading="exit3.loading" :disabled="busy || delivery.doc.exit3_receiving_cleared" @click="run(exit3, { delivery: delivery.doc.name }, __('The receiving was confirmed'))">{{ __("Clear Receiving") }}</Button>
      </div>
      <p v-if="capabilities.includes('clear_exit_1') && exit1Reason" class="feature-reason">{{ __("Clear Delivery Gate") }}: {{ exit1Reason }}</p>
      <p v-if="capabilities.includes('clear_exit_3') && exit3Reason" class="feature-reason">{{ __("Clear Receiving") }}: {{ exit3Reason }}</p>
      <form v-if="capabilities.includes('confirm_delivery_receipt') && delivery.doc.status === 'Released'" class="feature-form" @submit.prevent="run(receipt, { delivery: delivery.doc.name, code }, __('Receiving Confirmed'))">
        <!-- The six-digit rule lives only in the disabled expression, so a five-digit code left
             the receiver with a dead button and no rule to read. -->
        <FormControl v-model="code" :label="__('Receipt Code')" inputmode="numeric" :description="__('The receipt code is six digits.')" required />
        <Button type="submit" theme="green" variant="solid" :loading="receipt.loading" :disabled="code.length !== 6">{{ __("Mark Received") }}</Button>
      </form>
      <ErrorMessage v-if="error" :message="error" />
    </template>
  </section>
</template>
