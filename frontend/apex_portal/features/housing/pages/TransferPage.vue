<script setup>
import { computed, reactive, ref } from "vue";
import { Button, ErrorMessage, FormControl, createResource, toast } from "frappe-ui";
import { Link } from "frappe-ui/frappe";
import { safeErrorMessage } from "../../../core/errorMessage.js";
import { __ } from "../../../core/i18n.js";

const form = reactive({ source_bed: "", target_bed: "", reason: "" });
const error = ref("");
const transfer = createResource({ url: "apex.habitat.api.transfer_board.transfer_occupant" });
// Link marks its label required but enforces nothing, so both beds are checked here.
const canSubmit = computed(() => Boolean(form.source_bed && form.target_bed));
// `ErrorMessage` below only carries a rejected transfer, so without this the greyed button is the
// clerk's only signal that a bed is still unpicked.
const blockedReason = computed(() => {
  if (!form.source_bed) return __("Select the current bed to enable the transfer.");
  if (!form.target_bed) return __("Select the new bed to enable the transfer.");
  return "";
});
async function submit() {
  error.value = "";
  if (!canSubmit.value) return;
  try {
    await transfer.submit({ ...form });
    toast.create({ type: "success", message: __("The resident was transferred") });
    Object.assign(form, { source_bed: "", target_bed: "", reason: "" });
  } catch (exception) {
    error.value = safeErrorMessage(exception, __("Could not complete the transfer."));
  }
}
</script>
<template>
  <section class="feature-page"><h2>{{ __("Transfer Resident") }}</h2><form class="feature-form" @submit.prevent="submit">
    <Link v-model="form.source_bed" doctype="Bed" :label="__('Current Bed')" :placeholder="__('Search for the current bed')" required />
    <Link v-model="form.target_bed" doctype="Bed" :label="__('New Bed')" :placeholder="__('Search for the new bed')" required />
    <FormControl v-model="form.reason" type="textarea" :label="__('Transfer Reason')" />
    <ErrorMessage v-if="error" :message="error" />
    <p v-if="blockedReason" class="feature-state">{{ blockedReason }}</p>
    <Button type="submit" theme="green" variant="solid" :disabled="!canSubmit" :loading="transfer.loading">{{ __("Execute Transfer") }}</Button>
  </form></section>
</template>
