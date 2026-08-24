<script setup>
import { inject } from "vue";
import { Button, FormControl } from "frappe-ui";
import { createDraftAction } from "./asyncState.js";
import { __ } from "../../core/i18n.js";

const props = defineProps({ transport: { type: Boolean, default: false } });
const gateway = inject("workerGateway", null);
const drafts = inject("portalDrafts", null);
const requestTypes = [
  { label: __("Maintenance"), value: "Maintenance" },
  { label: __("safety"), value: "Safety" },
  { label: __("custody"), value: "Custody" },
  { label: __("Complaint"), value: "Complaint" },
  { label: __("Suggestion"), value: "Suggestion" },
];
const action = createDraftAction(props.transport
  ? { pickup_point: "", destination: "", travel_date: "", reason: "" }
  : { request_type: "Maintenance", subject: "", description: "" }, {
  store: drafts,
  key: props.transport ? "transport-request" : "service-request",
});

// The gateway is injected, so a page that renders this form outside the worker app has none.
// Say so in the page instead of failing on submit with an internal error.
const method = props.transport ? gateway?.createTransportRequest : gateway?.createRequest;
const unavailable = typeof method !== "function";

function save() {
  if (unavailable) return;
  return action.submit((values) => method(values));
}
</script>

<template>
  <section class="feature-page">
    <header class="feature-page__heading">
      <div><p class="feature-page__eyebrow">{{ __("New request") }}</p><h2>{{ transport ? __('Transport Request') : __('Service request') }}</h2></div>
    </header>
    <form class="feature-form" @submit.prevent="save">
      <template v-if="transport">
        <FormControl v-model="action.draft.pickup_point" :label="__('Departure Point')" required />
        <FormControl v-model="action.draft.destination" :label="__('Destination')" required />
        <FormControl v-model="action.draft.travel_date" type="date" :label="__('Date')" required />
        <FormControl v-model="action.draft.reason" type="textarea" :label="__('Reason')" />
      </template>
      <template v-else>
        <FormControl v-model="action.draft.request_type" type="select" :label="__('Request Type')" :options="requestTypes" />
        <FormControl v-model="action.draft.subject" :label="__('Subject')" required />
        <FormControl v-model="action.draft.description" type="textarea" :label="__('Details')" required />
      </template>
      <p v-if="unavailable" class="feature-error" role="alert">{{ __("Could not prepare the request form. Reload the page, and if it happens again contact your supervisor.") }}</p>
      <p v-else-if="action.state.value === 'error'" class="feature-error" role="alert">{{ action.error.value }}</p>
      <p v-if="action.state.value === 'saved'" class="feature-success" role="status">{{ __("The request has been sent.") }}</p>
      <div class="feature-actions">
        <Button type="submit" theme="green" variant="solid" :disabled="unavailable" :loading="action.state.value === 'saving'">{{ __("Send") }}</Button>
        <Button
          v-if="action.dirty.value"
          type="button"
          variant="outline"
          :disabled="action.state.value === 'saving'"
          @click="action.discard"
        >
          {{ __("Discard draft") }}
        </Button>
      </div>
    </form>
  </section>
</template>
