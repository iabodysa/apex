<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref } from "vue";
import { Badge, Button, ErrorMessage, FormControl, createResource, toast } from "frappe-ui";
import { useRoute } from "vue-router";
import { createQrScanner } from "./scanner.js";
import { dateTimeLabel, remainingSeconds, statusLabel, workerTransportStatusLabel } from "../../core/displayLabels.js";
import { errorStatus, safeErrorMessage } from "../../core/errorMessage.js";
import PortalSkeleton from "../../components/PortalSkeleton.vue";
import PortalErrorState from "../../components/PortalErrorState.vue";

const route = useRoute();
const gateway = inject("driverGateway");
const subscribe = inject("portalSubscribe", () => () => {});
const tripResource = createResource({
  url: "apex.salis.api.driver_portal.my_trip_route",
  method: "GET",
  auto: false,
});
const boardingResource = createResource({
  url: "apex.salis.api.boarding_flow.get_trip_boarding",
  method: "GET",
  auto: false,
});
const todayResource = createResource({
  url: "apex.salis.api.driver_portal.personal.get_masar_today",
  method: "GET",
  auto: false,
});
const scanner = createQrScanner();
const state = ref("loading");
const trip = ref(null);
const boarding = ref({ workers: [] });
const error = ref(null);
const busy = ref("");
const scanToken = ref("");
const scanResult = ref("");
const scannerVideo = ref(null);
const now = ref(Date.now());
let pollTimer;
let clockTimer;
let unsubscribers = [];

const dispatchTrip = computed(() => route.params.trip);
const statusByEmployee = computed(() => new Map((boarding.value?.workers || []).map((worker) => [worker.employee, worker])));
const workers = computed(() =>
  (trip.value?.workers || []).map((worker) => ({
    ...worker,
    ...(statusByEmployee.value.get(worker.employee) || { status: "Pending", wait_count: 0 }),
  })),
);
const pendingWorkers = computed(() => workers.value.filter((worker) => worker.status !== "Boarded"));
// Counted here rather than in the template: the clock ticks every second, and a template
// expression would re-scan both lists on every tick.
const boardedCount = computed(() => workers.value.filter((worker) => worker.status === "Boarded").length);
const completedStops = computed(() => (trip.value?.stops || []).filter((stop) => stop.done).length);
// A driver reads this on a phone, where a tooltip never appears, so every blocked action says why
// in the page itself. An empty string means the action is available.
const blocked = computed(() => ({
  start: trip.value?.started ? "الرحلة بدأت بالفعل." : "",
  finish: trip.value?.started ? "" : "ابدأ الرحلة أولاً.",
  notify: pendingWorkers.value.length ? "" : "لا أحد بانتظارك الآن.",
  depart: boarding.value?.grace_elapsed ? "" : "انتظر انتهاء مهلة الصعود قبل المغادرة.",
  scan: scanToken.value ? "" : "امسح بطاقة الراكب أو اكتب رمزها أولاً.",
}));
const waitLimit = computed(() => boarding.value?.worker_wait_request_max || 0);

function waitSeconds(worker) {
  return remainingSeconds(worker.wait_at, boarding.value?.worker_wait_request_seconds, now.value);
}

const scanMessages = Object.freeze({
  Valid: "تم تسجيل الصعود.",
  Duplicate: "تم تسجيل هذا الصعود من قبل.",
  "Wrong Trip": "البطاقة تخص رحلة أخرى.",
  Expired: "انتهت صلاحية بطاقة الصعود.",
  "Invalid Token": "بطاقة الصعود غير صحيحة.",
});

function stopLive() {
  clearInterval(pollTimer);
  clearInterval(clockTimer);
  while (unsubscribers.length) unsubscribers.pop()();
  scanner.stop();
}

function startLive(room) {
  while (unsubscribers.length) unsubscribers.pop()();
  if (room) {
    for (const event of ["boarding_update", "boarding_confirmed", "boarding_unmarked", "boarding_arrived", "wait_request"]) {
      unsubscribers.push(subscribe(room, event, () => load(true)) || (() => {}));
    }
  }
  clearInterval(pollTimer);
  pollTimer = setInterval(() => load(true), 10000);
}

async function load(quiet = false) {
  if (!quiet) state.value = "loading";
  error.value = null;
  try {
    const [tripData, boardingData, today] = await Promise.all([tripResource.fetch({ dispatch_trip: dispatchTrip.value }), boardingResource.fetch({ dispatch_trip: dispatchTrip.value }), todayResource.fetch()]);
    trip.value = tripData;
    boarding.value = boardingData || { workers: [] };
    state.value = tripData ? "ready" : "empty";
    startLive(today?.realtime_room || "");
  } catch (reason) {
    if (quiet) return;
    state.value = [401, 403].includes(errorStatus(reason)) ? "denied" : "error";
    error.value = reason;
  }
}

async function run(key, action, message) {
  busy.value = key;
  error.value = null;
  try {
    await action();
    toast.create({ type: "success", message });
    await load(true);
  } catch (reason) {
    error.value = reason;
  } finally {
    busy.value = "";
  }
}

async function submitScan(token = scanToken.value) {
  if (!token) return;
  busy.value = "scan";
  try {
    const result = await gateway.scanPass(token);
    scanResult.value = scanMessages[result?.result] || "تعذّر قراءة البطاقة.";
    if (["Valid", "Duplicate"].includes(result?.result)) await load(true);
  } catch (reason) {
    scanResult.value = safeErrorMessage(reason, "تعذّر تسجيل الصعود.");
  } finally {
    busy.value = "";
  }
}

async function startCamera() {
  try {
    await scanner.start(scannerVideo.value, submitScan);
  } catch (reason) {
    scanResult.value = safeErrorMessage(reason, "تعذّر تشغيل الكاميرا.");
  }
}

onMounted(() => {
  clockTimer = setInterval(() => {
    now.value = Date.now();
  }, 1000);
  load();
});
onBeforeUnmount(stopLive);
</script>

<template>
  <section class="feature-page journey-page driver-journey" :aria-busy="state === 'loading'">
    <header class="feature-page__heading journey-heading">
      <div>
        <p class="feature-page__eyebrow">تنفيذ الرحلة</p>
        <h2>{{ trip?.route_name || "خط السير" }}</h2>
        <p>المحطات والركاب في شاشة واحدة.</p>
      </div>
      <Badge v-if="trip" :label="statusLabel(trip.status)" />
    </header>

    <PortalSkeleton v-if="state === 'loading'" :rows="3" label="جارٍ تجهيز الرحلة" />
    <PortalErrorState v-else-if="state === 'denied'" title="تعذّر فتح الرحلة" :message="error" fallback="هذه الرحلة غير متاحة لحسابك." @retry="load()" />
    <PortalErrorState v-else-if="state === 'error'" title="تعذّر تحميل الرحلة" :message="error" fallback="تعذّر تحميل الرحلة." @retry="load()" />
    <div v-else-if="state === 'empty'" class="feature-state">لا توجد بيانات لهذه الرحلة.</div>

    <template v-else>
      <ErrorMessage v-if="error" :message="safeErrorMessage(error, 'تعذّر تنفيذ الإجراء.')" />
      <section class="journey-command">
        <div class="journey-command__metric">
          <strong>{{ boardedCount }}</strong>
          <span>صعد</span>
        </div>
        <div class="journey-command__metric">
          <strong>{{ pendingWorkers.length }}</strong>
          <span>بانتظارك</span>
        </div>
        <div class="journey-command__metric">
          <strong>{{ completedStops }}</strong>
          <span>محطة مكتملة</span>
        </div>
        <div class="journey-actions journey-command__actions">
          <Button theme="green" variant="solid" :disabled="trip.started" :loading="busy === 'start'" @click="run('start', () => gateway.startTrip(dispatchTrip), 'بدأت الرحلة')">بدء الرحلة</Button>
          <Button variant="outline" :disabled="!trip.started" :loading="busy === 'finish'" @click="run('finish', () => gateway.finishTrip(dispatchTrip), 'انتهت الرحلة')">إنهاء الرحلة</Button>
        </div>
        <p v-if="blocked.start || blocked.finish" class="journey-hint">{{ blocked.start || blocked.finish }}</p>
      </section>

      <section class="journey-section">
        <div class="journey-section__title">
          <h3>المحطات</h3>
          <a v-if="trip.maps_route_url" class="journey-link" :href="trip.maps_route_url" target="_blank" rel="noopener">افتح الخريطة</a>
        </div>
        <ol class="driver-timeline">
          <li v-for="(stop, index) in trip.stops || []" :key="stop.route_stop || index" :class="{ 'is-done': stop.done }">
            <span class="driver-timeline__number">{{ index + 1 }}</span>
            <div class="driver-timeline__copy">
              <strong>{{ stop.stop_name || stop.location || "محطة" }}</strong>
              <small>
                {{ stop.arrived ? "وصلت" : stop.done ? "اكتملت" : "قادمة" }}
                <template v-if="stop.planned_time">
                  ·
                  <bdi>{{ dateTimeLabel(stop.planned_time) }}</bdi>
                </template>
              </small>
              <div v-if="stop.pickup" class="driver-stop-meta">
                <span v-if="stop.pickup.building_name">{{ stop.pickup.building_name }}</span>
                <span v-if="stop.pickup.city">{{ stop.pickup.city }}</span>
                <a v-if="stop.pickup.google_maps_url" :href="stop.pickup.google_maps_url" target="_blank" rel="noopener">افتح موقع المحطة</a>
              </div>
            </div>
            <div class="journey-actions">
              <Button variant="outline" :disabled="!trip.started || stop.arrived" :loading="busy === `arrive:${stop.route_stop}`" @click="run(`arrive:${stop.route_stop}`, () => gateway.arriveAtStop(dispatchTrip, stop.route_stop), 'تم تنبيه المنتظرين بوصولك')">وصلت</Button>
              <Button variant="outline" :disabled="!trip.started" :loading="busy === `stop:${stop.route_stop}`" @click="run(`stop:${stop.route_stop}`, () => gateway.setStopProgress(dispatchTrip, stop.route_stop, !stop.done), stop.done ? 'أعيدت المحطة إلى المسار' : 'اكتملت المحطة')">{{ stop.done ? "إلغاء اكتمال المحطة" : "غادرت المحطة" }}</Button>
            </div>
          </li>
        </ol>
        <p v-if="!(trip.stops || []).length" class="feature-state">لا توجد محطات مخططة لهذه الرحلة.</p>
      </section>

      <section class="journey-section">
        <div class="journey-section__title">
          <h3>الركاب</h3>
          <span>{{ workers.length }}</span>
        </div>
        <article v-for="worker in workers" :key="worker.employee" class="passenger-row" :class="{ 'has-wait': worker.wait_count }">
          <div>
            <strong>{{ worker.employee_name || worker.employee }}</strong>
            <small>{{ worker.pickup_point || "نقطة التجمع" }}</small>
            <a v-if="worker.phone" class="passenger-call" :href="`tel:${worker.phone}`">اتصل بالعامل</a>
          </div>
          <span v-if="worker.wait_count" class="wait-signal">
            طلب الانتظار {{ worker.wait_count }} من {{ waitLimit }}
            <template v-if="waitSeconds(worker) !== null">· {{ waitSeconds(worker) }} ث</template>
          </span>
          <Badge :label="workerTransportStatusLabel(worker.status)" />
          <div class="journey-actions">
            <Button v-if="worker.status !== 'Boarded'" variant="outline" :loading="busy === `manual:${worker.employee}`" @click="run(`manual:${worker.employee}`, () => gateway.manualBoard(dispatchTrip, worker.employee), 'تم تسجيل الصعود يدوياً')">تسجيل يدوي</Button>
            <Button v-else variant="outline" :loading="busy === `unmark:${worker.employee}`" @click="run(`unmark:${worker.employee}`, () => gateway.markNotBoarded(dispatchTrip, worker.employee), 'أعيد العامل إلى قائمة الانتظار')">ليس في الحافلة</Button>
          </div>
        </article>
        <p v-if="!workers.length" class="feature-state">لا يوجد ركاب مسجلون لهذه الرحلة.</p>
        <div class="journey-actions">
          <Button variant="outline" :disabled="!pendingWorkers.length" :loading="busy === 'notify'" @click="run('notify', () => gateway.notifyPassengers(dispatchTrip), 'تم تنبيه المتبقين')">نبه المتبقين</Button>
          <Button theme="green" variant="solid" :disabled="!boarding.grace_elapsed" :loading="busy === 'depart'" @click="run('depart', () => gateway.depart(dispatchTrip), 'أغلق الصعود وغادرت الحافلة')">أغلق الصعود وغادر</Button>
        </div>
        <p v-if="blocked.depart || blocked.notify" class="journey-hint">{{ blocked.depart || blocked.notify }}</p>
      </section>

      <section class="journey-section scanner-panel">
        <div class="journey-section__title">
          <h3>بطاقة الصعود</h3>
          <span>رمز سريع</span>
        </div>
        <video ref="scannerVideo" muted playsinline></video>
        <FormControl v-model="scanToken" label="رمز البطاقة" autocomplete="off" />
        <div class="journey-actions">
          <Button variant="outline" @click="startCamera">افتح الكاميرا</Button>
          <Button theme="green" variant="solid" :disabled="!scanToken" :loading="busy === 'scan'" @click="submitScan()">سجل الصعود</Button>
        </div>
        <p v-if="blocked.scan" class="journey-hint">{{ blocked.scan }}</p>
        <p v-if="scanResult" role="status">{{ scanResult }}</p>
      </section>
    </template>
  </section>
</template>
