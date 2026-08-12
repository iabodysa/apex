<script setup>
import { inject } from "vue";
import { Button, FormControl } from "frappe-ui";
import { createDraftAction } from "../worker/asyncState.js";

const gateway = inject("transportSupervisorGateway", null);
const action = createDraftAction({ route_name: "", project: "", shift: "", driver: "", vehicle: "" });

function save() { return action.submit((values) => gateway.createPlan(values)); }
</script>

<template>
  <section class="feature-page">
    <header class="feature-page__heading"><div><p class="feature-page__eyebrow">تشغيل النقل</p><h2>خطة مسار جديدة</h2><p>أنشئ الخطة ثم أكمل نقاط التوقف من مستندها.</p></div></header>
    <form class="feature-form" @submit.prevent="save">
      <FormControl v-model="action.draft.route_name" label="اسم المسار" required />
      <FormControl v-model="action.draft.project" label="المشروع" required />
      <FormControl v-model="action.draft.shift" label="الشفت" />
      <FormControl v-model="action.draft.driver" label="السائق" />
      <FormControl v-model="action.draft.vehicle" label="المركبة" />
      <p v-if="action.state.value === 'error'" class="feature-error" role="alert">{{ action.error.value }}</p>
      <p v-if="action.state.value === 'saved'" class="feature-success" role="status">تم حفظ الخطة.</p>
      <Button type="submit" variant="solid" :loading="action.state.value === 'saving'">حفظ</Button>
    </form>
  </section>
</template>
