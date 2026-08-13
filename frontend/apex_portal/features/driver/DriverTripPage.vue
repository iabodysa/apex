<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref } from "vue";
import { Badge, Button, ErrorMessage, FormControl, LoadingIndicator, toast } from "frappe-ui";
import { useRoute } from "vue-router";
import { createQrScanner } from "./scanner.js";
import { statusLabel } from "../../core/displayLabels.js";

const route = useRoute();
const gateway = inject("driverGateway");
const subscribe = inject("portalSubscribe", () => () => {});
const scanner = createQrScanner();
const state = ref("loading");
const trip = ref(null);
const boarding = ref({ workers: [] });
const error = ref("");
const busy = ref("");
const scanToken = ref("");
const scanResult = ref("");
const scannerVideo = ref(null);
let pollTimer;
let unsubscribers = [];

const dispatchTrip = computed(() => route.params.trip);
const statusByEmployee = computed(() => new Map(
  (boarding.value?.workers || []).map((worker) => [worker.employee, worker]),
));
const workers = computed(() => (trip.value?.workers || []).map((worker) => ({
  ...worker,
  ...(statusByEmployee.value.get(worker.employee) || { status: "Pending", wait_count: 0 }),
})));
const pendingWorkers = computed(() => workers.value.filter((worker) => worker.status !== "Boarded"));

const statusLabels = Object.freeze({
  Pending: "بانتظار الصعود",
  Boarded: "صعد",
  Absent: "لم يصعد",
  "Worker Claimed": "أكد صعوده",
});
const scanMessages = Object.freeze({
  Valid: "تم تسجيل الصعود.",
  Duplicate: "تم تسجيل هذا الصعود من قبل.",
  "Wrong Trip": "البطاقة تخص رحلة أخرى.",
  Expired: "انتهت صلاحية بطاقة الصعود.",
  "Invalid Token": "بطاقة الصعود غير صحيحة.",
});

function stopLive() {
  clearInterval(pollTimer);
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
  error.value = "";
  try {
    const [tripData, boardingData, today] = await Promise.all([
      gateway.trip(dispatchTrip.value),
      gateway.tripBoarding(dispatchTrip.value),
      gateway.today(),
    ]);
    trip.value = tripData;
    boarding.value = boardingData || { workers: [] };
    state.value = tripData ? "ready" : "empty";
    startLive(today?.realtime_room || "");
  } catch (reason) {
    if (quiet) return;
    state.value = reason?.status === 403 ? "denied" : "error";
    error.value = reason?.message || "تعذّر تحميل الرحلة.";
  }
}

async function run(key, action, message) {
  busy.value = key;
  error.value = "";
  try {
    await action();
    toast({ title: message, icon: "check" });
    await load(true);
  } catch (reason) {
    error.value = reason?.message || "تعذّر تنفيذ الإجراء.";
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
    scanResult.value = reason?.message || "تعذّر تسجيل الصعود.";
  } finally {
    busy.value = "";
  }
}

async function startCamera() {
  try {
    await scanner.start(scannerVideo.value, submitScan);
  } catch (reason) {
    scanResult.value = reason?.message || "تعذّر تشغيل الكاميرا.";
  }
}

onMounted(load);
onBeforeUnmount(stopLive);
</script>

<template>
  <section class="feature-page journey-page driver-journey" :aria-busy="state === 'loading'">
    <header class="feature-page__heading journey-heading">
      <div><p class="feature-page__eyebrow">تنفيذ الرحلة</p><h2>{{ trip?.route_name || 'خط السير' }}</h2><p>المحطات والركاب في شاشة واحدة.</p></div>
      <Badge v-if="trip" :label="statusLabel(trip.status)" />
    </header>

    <div v-if="state === 'loading'" class="feature-state" role="status"><LoadingIndicator /> جارٍ تجهيز الرحلة…</div>
    <div v-else-if="state === 'denied'" class="feature-state">هذه الرحلة غير متاحة لحسابك.</div>
    <div v-else-if="state === 'error'" class="feature-state feature-state--error"><ErrorMessage :message="error" /><Button variant="outline" @click="load()">إعادة المحاولة</Button></div>
    <div v-else-if="state === 'empty'" class="feature-state">لا توجد بيانات لهذه الرحلة.</div>

    <template v-else>
      <ErrorMessage v-if="error" :message="error" />
      <section class="journey-command">
        <div class="journey-command__metric"><strong>{{ workers.filter((worker) => worker.status === 'Boarded').length }}</strong><span>صعد</span></div>
        <div class="journey-command__metric"><strong>{{ pendingWorkers.length }}</strong><span>بانتظارك</span></div>
        <div class="journey-command__metric"><strong>{{ trip.stops?.filter((stop) => stop.done).length || 0 }}</strong><span>محطة مكتملة</span></div>
        <div class="journey-actions journey-command__actions">
          <Button theme="green" variant="solid" :disabled="trip.started" :loading="busy === 'start'" @click="run('start', () => gateway.startTrip(dispatchTrip), 'بدأت الرحلة')">بدء الرحلة</Button>
          <Button variant="outline" :disabled="!trip.started" :loading="busy === 'finish'" @click="run('finish', () => gateway.finishTrip(dispatchTrip), 'انتهت الرحلة')">إنهاء الرحلة</Button>
        </div>
      </section>

      <section class="journey-section">
        <div class="journey-section__title"><h3>المحطات</h3><a v-if="trip.maps_route_url" class="journey-link" :href="trip.maps_route_url" target="_blank" rel="noopener">افتح الخريطة</a></div>
        <ol class="driver-timeline">
          <li v-for="(stop, index) in trip.stops || []" :key="stop.route_stop || index" :class="{ 'is-done': stop.done }">
            <span class="driver-timeline__number">{{ index + 1 }}</span>
            <div class="driver-timeline__copy"><strong>{{ stop.stop_name || stop.location || 'محطة' }}</strong><small>{{ stop.arrived ? 'وصلت' : stop.done ? 'اكتملت' : 'قادمة' }}</small></div>
            <div class="journey-actions">
              <Button variant="outline" :disabled="!trip.started || stop.arrived" :loading="busy === `arrive:${stop.route_stop}`" @click="run(`arrive:${stop.route_stop}`, () => gateway.arriveAtStop(dispatchTrip, stop.route_stop), 'تم تنبيه المنتظرين بوصولك')">وصلت</Button>
              <Button variant="outline" :disabled="!trip.started || stop.done" :loading="busy === `stop:${stop.route_stop}`" @click="run(`stop:${stop.route_stop}`, () => gateway.markStop(dispatchTrip, stop.route_stop), 'اكتملت المحطة')">غادرت المحطة</Button>
            </div>
          </li>
        </ol>
      </section>

      <section class="journey-section">
        <div class="journey-section__title"><h3>الركاب</h3><span>{{ workers.length }}</span></div>
        <article v-for="worker in workers" :key="worker.employee" class="passenger-row" :class="{ 'has-wait': worker.wait_count }">
          <div><strong>{{ worker.employee_name || worker.employee }}</strong><small>{{ worker.pickup_point || 'نقطة التجمع' }}</small></div>
          <span v-if="worker.wait_count" class="wait-signal">يطلب الانتظار</span>
          <Badge :label="statusLabels[worker.status] || worker.status" />
          <div class="journey-actions">
            <Button v-if="worker.status !== 'Boarded'" variant="outline" :loading="busy === `manual:${worker.employee}`" @click="run(`manual:${worker.employee}`, () => gateway.manualBoard(dispatchTrip, worker.employee), 'تم تسجيل الصعود يدوياً')">تسجيل يدوي</Button>
            <Button v-else variant="outline" :loading="busy === `unmark:${worker.employee}`" @click="run(`unmark:${worker.employee}`, () => gateway.markNotBoarded(dispatchTrip, worker.employee), 'أعيد العامل إلى قائمة الانتظار')">ليس في الحافلة</Button>
          </div>
        </article>
        <div class="journey-actions">
          <Button variant="outline" :disabled="!pendingWorkers.length" :loading="busy === 'notify'" @click="run('notify', () => gateway.notifyPassengers(dispatchTrip), 'تم تنبيه المتبقين')">نبه المتبقين</Button>
          <Button theme="green" variant="solid" :disabled="!boarding.grace_elapsed" :loading="busy === 'depart'" @click="run('depart', () => gateway.depart(dispatchTrip), 'أغلق الصعود وغادرت الحافلة')">أغلق الصعود وغادر</Button>
        </div>
      </section>

      <section class="journey-section scanner-panel">
        <div class="journey-section__title"><h3>بطاقة الصعود</h3><span>رمز سريع</span></div>
        <video ref="scannerVideo" muted playsinline></video>
        <FormControl v-model="scanToken" label="رمز البطاقة" autocomplete="off" />
        <div class="journey-actions"><Button variant="outline" @click="startCamera">افتح الكاميرا</Button><Button theme="green" variant="solid" :disabled="!scanToken" :loading="busy === 'scan'" @click="submitScan()">سجل الصعود</Button></div>
        <p v-if="scanResult" role="status">{{ scanResult }}</p>
      </section>
    </template>
  </section>
</template>
