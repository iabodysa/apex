<script setup>
import { computed, inject, onBeforeUnmount, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Button, ErrorMessage, FormControl, createDocumentResource, createListResource, createResource, toast } from "frappe-ui";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import { housingCandidateFromQuery } from "../arrivalFlow.js";
import { statusLabel } from "../../../core/displayLabels.js";
import { safeErrorMessage } from "../../../core/errorMessage.js";

const route = useRoute();
const router = useRouter();
const error = ref("");
// The server signals the custody block structurally; matching its Arabic sentence for a
// substring made the shortcut unreachable and would have fired on unrelated errors too.
const custodyBlocked = ref(false);
const checkInForm = reactive({ party_type: "Employee", party: "", project: "" });
const capabilities = globalThis.window?.apex_portal?.capabilities || [];
const canCheckIn = capabilities.includes("check_in");
const canCheckOut = capabilities.includes("check_out");
const bed = createDocumentResource({ doctype: "Bed", name: route.params.bed });
const projects = createListResource({
  doctype: "Project",
  fields: ["name", "project_name"],
  orderBy: "project_name asc",
  pageLength: 200,
  auto: canCheckIn,
});
const checkIn = createResource({ url: "apex.habitat.api.front_desk.quick_check_in" });
const checkOut = createResource({ url: "apex.habitat.api.front_desk.quick_check_out" });
const occupied = computed(() => bed.doc?.status === "Occupied");
const candidate = computed(() => housingCandidateFromQuery(route.query));
// The two explanations further down belong to the no-permission branches, which do not render
// while this form is on screen — so a greyed "تسكين" had nothing beside it.
const checkInReason = computed(() => {
  if (!checkInForm.party) return "اكتب رقم الساكن لتفعيل التسكين.";
  if (!checkInForm.project) return "اختر المشروع لتفعيل التسكين.";
  return "";
});
const projectOptions = computed(() => (projects.data || []).map((project) => ({
  label: project.project_name || project.name,
  value: project.name,
})));
watch(candidate, (value) => {
  Object.assign(checkInForm, value
    ? { party_type: value.party_type, party: value.party, project: value.project }
    : { party_type: "Employee", party: "", project: "" });
}, { immediate: true });

const subscribeBuilding = inject("portalBuildingSubscribe", () => () => {});
let pollTimer;
let unsubscribers = [];
let liveBuilding = null;

function stopLive() {
  clearInterval(pollTimer);
  liveBuilding = null;
  while (unsubscribers.length) unsubscribers.pop()();
}

// Called whenever the loaded bed's building becomes known or changes, so it must be a no-op
// while the room already holds it — otherwise a poll tick would tear the listener down and
// rebuild it.
function startLive(name) {
  if (name === liveBuilding) return;
  liveBuilding = name;
  while (unsubscribers.length) unsubscribers.pop()();
  if (name) unsubscribers.push(subscribeBuilding(name, "doc_update", () => bed.reload()) || (() => {}));
  clearInterval(pollTimer);
  pollTimer = setInterval(() => bed.doc?.building && bed.reload(), 10000);
}

watch(() => bed.doc?.building, startLive, { immediate: true });
onBeforeUnmount(stopLive);
async function arrive() {
  error.value = "";
  try {
    await checkIn.submit({ bed: route.params.bed, ...checkInForm });
    toast.create({ type: "success", message: "تم تسكين العامل" });
    Object.assign(checkInForm, { party_type: "Employee", party: "", project: "" });
    await bed.reload();
    if (candidate.value) await router.push("/arrivals");
  } catch (exception) { error.value = safeErrorMessage(exception, "تعذر التسكين."); }
}
async function depart() {
  error.value = "";
  custodyBlocked.value = false;
  try {
    const response = await checkOut.submit({ bed: route.params.bed, checkout_reason: "End of Contract" });
    if (response?.requires_full_form) {
      error.value = "يجب استلام عهد العامل قبل إتمام المغادرة.";
      custodyBlocked.value = true;
      return;
    }
    toast.create({ type: "success", message: "تم تسجيل المغادرة" });
    await bed.reload();
  } catch (exception) { error.value = safeErrorMessage(exception, "تعذر تسجيل المغادرة."); }
}
</script>

<template>
  <section class="feature-page">
    <h2>تفاصيل السرير</h2>
    <PortalSkeleton v-if="bed.get.loading && !bed.doc" :rows="3" label="جارٍ التحميل" />
    <ErrorMessage v-else-if="bed.get.error" message="تعذر تحميل السرير." />
    <template v-else-if="bed.doc">
      <article class="feature-card"><strong><bdi dir="auto" translate="no">{{ bed.doc.bed_code || bed.doc.name }}</bdi></strong><span><bdi dir="auto" translate="no">{{ bed.doc.room }}</bdi></span><small>{{ statusLabel(bed.doc.status) }} · {{ statusLabel(bed.doc.condition) }}</small></article>
      <form v-if="!occupied && canCheckIn" class="feature-form" @submit.prevent="arrive">
        <article v-if="candidate" class="selected-resident">
          <div><span>الساكن المحدد</span><strong dir="auto">{{ candidate.label }}</strong><small v-if="candidate.project" dir="auto">{{ candidate.project }}</small></div>
          <RouterLink to="/arrivals">تغيير العامل</RouterLink>
        </article>
        <template v-else>
          <FormControl v-model="checkInForm.party_type" type="select" label="نوع الساكن" :options="[{ label: 'موظف', value: 'Employee' }, { label: 'عامل مؤقت', value: 'Temporary Worker' }]" />
          <FormControl v-model="checkInForm.party" label="رقم الساكن" required />
        </template>
        <FormControl v-if="!candidate?.project" v-model="checkInForm.project" type="select" label="المشروع" :options="projectOptions" required />
        <p v-if="checkInReason" class="feature-page__empty">{{ checkInReason }}</p>
        <Button type="submit" theme="green" variant="solid" :loading="checkIn.loading" :disabled="!checkInForm.party || !checkInForm.project">{{ candidate ? `تسكين ${candidate.label}` : 'تسكين' }}</Button>
      </form>
      <p v-else-if="!occupied" class="feature-page__empty">ليس لديك صلاحية تسكين عامل.</p>
      <Button v-else-if="canCheckOut" theme="green" variant="solid" :loading="checkOut.loading" @click="depart">تسجيل المغادرة</Button>
      <p v-else class="feature-page__empty">السرير مشغول، وليس لديك صلاحية تسجيل المغادرة.</p>
      <ErrorMessage v-if="error" :message="error" />
      <RouterLink v-if="custodyBlocked" to="/custody">الانتقال إلى العهد</RouterLink>
    </template>
  </section>
</template>
