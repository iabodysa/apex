<script setup>
import { inject } from "vue";
import { Button, FormControl } from "frappe-ui";
import { createDraftAction } from "./asyncState.js";

const props = defineProps({ transport: { type: Boolean, default: false } });
const gateway = inject("workerGateway", null);
const drafts = inject("portalDrafts", null);
const requestTypes = [
  { label: "صيانة", value: "Maintenance" },
  { label: "سلامة", value: "Safety" },
  { label: "عهدة", value: "Custody" },
  { label: "شكوى", value: "Complaint" },
  { label: "اقتراح", value: "Suggestion" },
];
const action = createDraftAction(props.transport
  ? { pickup_point: "", destination: "", travel_date: "", reason: "" }
  : { request_type: "Maintenance", subject: "", description: "" }, {
  store: drafts,
  key: props.transport ? "transport-request" : "service-request",
});

function save() {
  const method = props.transport ? gateway?.createTransportRequest : gateway?.createRequest;
  return action.submit((values) => method(values));
}
</script>

<template>
  <section class="feature-page">
    <header class="feature-page__heading">
      <div><p class="feature-page__eyebrow">طلب جديد</p><h2>{{ transport ? 'طلب نقل' : 'طلب خدمة' }}</h2></div>
    </header>
    <form class="feature-form" @submit.prevent="save">
      <template v-if="transport">
        <FormControl v-model="action.draft.pickup_point" label="نقطة الانطلاق" required />
        <FormControl v-model="action.draft.destination" label="الوجهة" required />
        <FormControl v-model="action.draft.travel_date" type="date" label="التاريخ" required />
        <FormControl v-model="action.draft.reason" type="textarea" label="السبب" />
      </template>
      <template v-else>
        <FormControl v-model="action.draft.request_type" type="select" label="نوع الطلب" :options="requestTypes" />
        <FormControl v-model="action.draft.subject" label="الموضوع" required />
        <FormControl v-model="action.draft.description" type="textarea" label="التفاصيل" required />
      </template>
      <p v-if="action.state.value === 'error'" class="feature-error" role="alert">{{ action.error.value }}</p>
      <p v-if="action.state.value === 'saved'" class="feature-success" role="status">تم إرسال الطلب.</p>
      <Button type="submit" theme="green" variant="solid" :loading="action.state.value === 'saving'">إرسال</Button>
    </form>
  </section>
</template>
