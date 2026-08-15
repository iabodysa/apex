<script setup>
import { computed, reactive, ref, watch } from "vue";
import { Button, FormControl, createListResource, createResource } from "frappe-ui";
import { safeErrorMessage } from "../../../core/errorMessage.js";
import { buildAdHocRequest } from "../assignmentState.js";

const props = defineProps({ request: { type: Object, required: true } });
const emit = defineEmits(["saved"]);

const trips = createListResource({
  doctype: "Dispatch Trip",
  fields: ["name", "trip_title", "trip_date", "project", "status"],
  filters: { status: "Planned" },
  orderBy: "trip_date asc, planned_start asc, modified desc",
  pageLength: 50,
  auto: false,
});
const tripRecord = createResource({ url: "frappe.client.get", method: "GET", auto: false });
const assign = createResource({
  url: "apex.salis.doctype.dispatch_trip.dispatch_trip.assign_requests_to_trip",
  method: "POST",
  auto: false,
});
const createAdHoc = createResource({
  url: "apex.salis.doctype.dispatch_trip.dispatch_trip.create_ad_hoc_trip",
  method: "POST",
  auto: false,
});
const selectedTrip = ref("");
const pickupStop = ref("");
const dropoffStop = ref("");
const existingError = ref("");
const tripListError = ref("");
const adHocError = ref("");
const notice = ref("");
const tripStopsByName = reactive({});
const savingExisting = ref(false);
const savingAdHoc = ref(false);
let stopLoadGeneration = 0;
const pickupDateTime = String(props.request.pickup_datetime || "")
  .trim()
  .replace(" ", "T")
  .slice(0, 19);
const adHoc = reactive({
  trip_date: pickupDateTime.slice(0, 10),
  planned_start: pickupDateTime,
  planned_end: "",
});

const needsApproval = computed(() => props.request.status === "Validated");
const tripOptions = computed(() => [
  { label: "اختر رحلة مخططة", value: "" },
  ...(trips.data || []).map((trip) => ({
    value: trip.name,
    label: trip.trip_title || `${trip.trip_date || "رحلة"} · ${trip.project || trip.name}`,
  })),
]);
const stops = computed(() => tripStopsByName[selectedTrip.value] || []);
const stopOptions = computed(() => [
  { label: "اختر نقطة توقف", value: "" },
  ...stops.value.map((stop) => ({ value: stop.stop_key, label: stop.stop_name || stop.stop_key })),
]);
// Both submits greyed on a compound condition and said nothing, so a supervisor who had filled
// three of four fields could not tell which one was still missing. The reason is the single source
// of truth: `can*` is its negation, so a live button and a rendered reason cannot both be true.
const assignReason = computed(() => {
  if (!selectedTrip.value) return "اختر الرحلة المخططة أولاً.";
  if (!pickupStop.value) return "حدد نقطة الصعود الفعلية.";
  if (!dropoffStop.value) return "حدد نقطة النزول الفعلية.";
  if (pickupStop.value === dropoffStop.value) return "اختر نقطتين مختلفتين للصعود والنزول.";
  return "";
});
const createReason = computed(() => {
  if (!adHoc.trip_date) return "حدد تاريخ الرحلة.";
  if (!adHoc.planned_start) return "حدد وقت البداية.";
  if (!adHoc.planned_end) return "حدد وقت النهاية.";
  return "";
});
const canAssign = computed(() => !assignReason.value);
const canCreate = computed(() => !createReason.value);

async function loadTrips() {
  tripListError.value = "";
  try {
    await trips.reload();
  } catch (reason) {
    tripListError.value = safeErrorMessage(
      reason,
      "تعذّر تحميل الرحلات المخططة. تحقق من صلاحية الرحلات ثم أعد المحاولة.",
    );
  }
}

async function loadMoreTrips() {
  tripListError.value = "";
  const previousStart = trips.start;
  try {
    trips.update({ start: previousStart + trips.pageLength });
    await trips.list.fetch();
  } catch (reason) {
    trips.update({ start: previousStart });
    tripListError.value = safeErrorMessage(reason, "تعذّر تحميل رحلات إضافية.");
  }
}

watch(selectedTrip, async (name) => {
  const generation = ++stopLoadGeneration;
  pickupStop.value = "";
  dropoffStop.value = "";
  existingError.value = "";
  if (!name) return;
  try {
    const result = await tripRecord.fetch({ doctype: "Dispatch Trip", name });
    if (generation !== stopLoadGeneration) return;
    tripStopsByName[name] = Array.isArray(result?.stops) ? result.stops : [];
    if (!stops.value.length) {
      existingError.value = "الرحلة المختارة لا تحتوي نقاط توقف فعلية. أضف التوقفات من سجل الرحلة أولاً.";
    }
  } catch (reason) {
    if (generation !== stopLoadGeneration) return;
    existingError.value = safeErrorMessage(reason, "تعذّر تحميل توقفات الرحلة المختارة.");
  }
});

async function assignExisting() {
  if (!canAssign.value || savingExisting.value) return;
  existingError.value = "";
  notice.value = "";
  savingExisting.value = true;
  try {
    const result = await assign.submit({
      dispatch_trip: selectedTrip.value,
      transport_requests: JSON.stringify([{
        transport_request: props.request.name,
        pickup_stop: pickupStop.value,
        dropoff_stop: dropoffStop.value,
      }]),
    });
    notice.value = "تم إسناد الطلب إلى الرحلة المخططة.";
    emit("saved", result);
  } catch (reason) {
    existingError.value = safeErrorMessage(reason, "تعذّر الإسناد. تحقق من أن الرحلة مخططة والطلب معتمد.");
  } finally {
    savingExisting.value = false;
  }
}

async function createTrip() {
  if (!canCreate.value || savingAdHoc.value) return;
  adHocError.value = "";
  notice.value = "";
  savingAdHoc.value = true;
  try {
    const payload = buildAdHocRequest(props.request, adHoc);
    const result = await createAdHoc.submit({
      trip: JSON.stringify(payload.trip),
      transport_requests: JSON.stringify(payload.transport_requests),
    });
    notice.value = "تم إنشاء الرحلة المخصصة وإسناد الطلب إليها.";
    emit("saved", result);
  } catch (reason) {
    adHocError.value = safeErrorMessage(reason, "تعذّر إنشاء الرحلة المخصصة. راجع المواقع والأوقات.");
  } finally {
    savingAdHoc.value = false;
  }
}

watch(needsApproval, (waitingForApproval, wasWaitingForApproval) => {
  if (!waitingForApproval && (wasWaitingForApproval !== false || !trips.data)) {
    void loadTrips();
  }
}, { immediate: true });
</script>

<template>
  <section class="supervisor-detail__section request-trip-planning">
    <header><h3>تخطيط الطلب</h3></header>
    <div v-if="needsApproval" class="feature-state request-trip-planning__approval" role="status">
      اعتمد الطلب أولاً من إجراء «اعتماد» أدناه؛ يقبل الإسناد التشغيلي الطلبات المعتمدة أو المجدولة فقط.
    </div>
    <template v-else>
      <p v-if="notice" class="feature-success" role="status">{{ notice }}</p>
      <div class="request-trip-planning__grid">
        <form class="request-trip-planning__panel" @submit.prevent="assignExisting">
          <div><p class="feature-page__eyebrow">رحلة قائمة</p><h4>إسناد إلى رحلة مخططة</h4></div>
          <div v-if="tripListError" class="feature-error" role="alert">
            <p>{{ tripListError }}</p>
            <Button type="button" variant="outline" @click="loadTrips">إعادة تحميل الرحلات</Button>
          </div>
          <FormControl v-model="selectedTrip" type="select" label="الرحلة" :options="tripOptions" required />
          <FormControl v-model="pickupStop" type="select" label="نقطة الصعود الفعلية" :options="stopOptions" :disabled="!selectedTrip" :description="selectedTrip ? '' : 'اختر الرحلة أولاً لتظهر نقاط توقفها.'" required />
          <FormControl v-model="dropoffStop" type="select" label="نقطة النزول الفعلية" :options="stopOptions" :disabled="!selectedTrip" :description="selectedTrip ? '' : 'اختر الرحلة أولاً لتظهر نقاط توقفها.'" required />
          <p v-if="existingError" class="feature-error" role="alert">{{ existingError }}</p>
          <p v-if="assignReason" class="feature-reason">{{ assignReason }}</p>
          <Button type="submit" theme="green" variant="solid" :loading="savingExisting" :disabled="!canAssign || savingExisting">إسناد إلى الرحلة</Button>
          <Button v-if="trips.hasNextPage" type="button" variant="outline" :loading="trips.list.loading" @click="loadMoreTrips">تحميل رحلات أخرى</Button>
        </form>

        <form class="request-trip-planning__panel" @submit.prevent="createTrip">
          <div><p class="feature-page__eyebrow">رحلة مخصصة</p><h4>إنشاء رحلة من الطلب</h4></div>
          <p>ينشئ النظام نقطتي انطلاق ووجهة فعليتين من بيانات الطلب ثم يسندهما معاً.</p>
          <FormControl v-model="adHoc.trip_date" type="date" label="تاريخ الرحلة" required />
          <FormControl v-model="adHoc.planned_start" type="datetime-local" label="وقت البداية" required />
          <FormControl v-model="adHoc.planned_end" type="datetime-local" label="وقت النهاية" required />
          <p v-if="adHocError" class="feature-error" role="alert">{{ adHocError }}</p>
          <p v-if="createReason" class="feature-reason">{{ createReason }}</p>
          <Button type="submit" theme="green" variant="solid" :loading="savingAdHoc" :disabled="!canCreate || savingAdHoc">إنشاء وإسناد</Button>
        </form>
      </div>
    </template>
  </section>
</template>
