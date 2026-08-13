<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref } from "vue";
import { Badge, Button, ErrorMessage, LoadingIndicator, toast } from "frappe-ui";
import QRCode from "qrcode";
import { dateTimeLabel } from "../../core/displayLabels.js";

const gateway = inject("workerGateway");
const subscribe = inject("portalSubscribe", () => () => {});
const state = ref("loading");
const transport = ref({ upcoming: [], past: [] });
const boarding = ref(null);
const error = ref("");
const busy = ref("");
const pass = ref(null);
const passImage = ref("");
let pollTimer;
let activeRoom = "";
let unsubscribers = [];

const trips = computed(() => transport.value?.upcoming || []);
const pastTrips = computed(() => transport.value?.past || []);
const hasContent = computed(() => trips.value.length || pastTrips.value.length || boarding.value?.dispatch_trip);
const canWait = computed(() => (
  boarding.value?.dispatch_trip
  && !["Boarded", "Absent"].includes(boarding.value.status)
  && Number(boarding.value.wait_count || 0) < Number(boarding.value.wait_max || 0)
));
const canConfirm = computed(() => (
  boarding.value?.boarding_window?.can_confirm
  && boarding.value.status !== "Boarded"
));

const statusLabels = Object.freeze({
  Pending: "بانتظار الصعود",
  Boarded: "تم الصعود",
  Absent: "لم يصعد",
  scheduled: "الرحلة مجدولة",
  en_route: "الحافلة في الطريق",
  at_stop: "الحافلة عند نقطة التجمع",
  departed: "غادرت الحافلة النقطة",
  finished: "انتهت الرحلة",
});
const statusLabel = (value) => statusLabels[value] || value || "بانتظار التحديث";

function stopLive() {
  clearInterval(pollTimer);
  pollTimer = undefined;
  while (unsubscribers.length) unsubscribers.pop()();
  activeRoom = "";
}

function startLive(room, seconds) {
  if (room && room !== activeRoom) {
    while (unsubscribers.length) unsubscribers.pop()();
    activeRoom = room;
    for (const event of ["driver_trip_update", "boarding_update", "boarding_confirmed", "boarding_unmarked", "boarding_arrived"]) {
      unsubscribers.push(subscribe(room, event, () => load(true)) || (() => {}));
    }
  }
  clearInterval(pollTimer);
  if (boarding.value?.dispatch_trip && !["Boarded", "Absent"].includes(boarding.value.status)) {
    pollTimer = setInterval(() => load(true), Math.max(Number(seconds) || 10, 5) * 1000);
  }
}

async function load(quiet = false) {
  if (!quiet) state.value = "loading";
  error.value = "";
  try {
    const [transportData, boardingData, context] = await Promise.all([
      gateway.transport(),
      gateway.boarding(),
      gateway.profile(),
    ]);
    transport.value = transportData || { upcoming: [], past: [] };
    boarding.value = boardingData || null;
    state.value = hasContent.value ? "ready" : "empty";
    startLive(context?.realtime_room || "", boarding.value?.poll_seconds);
  } catch (reason) {
    if (quiet) return;
    state.value = reason?.status === 403 ? "denied" : "error";
    error.value = reason?.message || "تعذّر تحميل الرحلات.";
  }
}

async function run(key, action, message) {
  busy.value = key;
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

async function showPass(request) {
  busy.value = `pass:${request}`;
  error.value = "";
  try {
    const result = await gateway.boardingPass(request);
    pass.value = result?.pass || null;
    passImage.value = pass.value?.qr_payload
      ? await QRCode.toDataURL(pass.value.qr_payload, { margin: 1, width: 320 })
      : "";
  } catch (reason) {
    error.value = reason?.message || "تعذّر عرض بطاقة الصعود.";
  } finally {
    busy.value = "";
  }
}

onMounted(load);
onBeforeUnmount(stopLive);
</script>

<template>
  <section class="feature-page journey-page" :aria-busy="state === 'loading'">
    <header class="feature-page__heading journey-heading">
      <div>
        <p class="feature-page__eyebrow">رحلات مسار</p>
        <h2>رحلتك من الباب إلى المقعد</h2>
        <p>تابع وصول الحافلة، اطلب من السائق الانتظار، ثم أكد صعودك.</p>
      </div>
    </header>

    <div v-if="state === 'loading'" class="feature-state" role="status"><LoadingIndicator /> جارٍ تحميل الرحلة…</div>
    <div v-else-if="state === 'denied'" class="feature-state">هذا القسم غير متاح لحسابك.</div>
    <div v-else-if="state === 'error'" class="feature-state feature-state--error">
      <ErrorMessage :message="error" /><Button variant="outline" @click="load()">إعادة المحاولة</Button>
    </div>
    <div v-else-if="state === 'empty'" class="feature-state">
      <strong>يومك هادئ</strong><p>لا توجد رحلة مجدولة لك حالياً.</p>
    </div>

    <template v-else>
      <ErrorMessage v-if="error" :message="error" />
      <article v-if="boarding?.dispatch_trip" class="journey-live" aria-live="polite">
        <div class="journey-live__top">
          <div>
            <span class="journey-kicker">الحالة الآن</span>
            <h3>{{ statusLabel(boarding.boarding_window?.state || boarding.status) }}</h3>
          </div>
          <Badge :label="statusLabel(boarding.status)" />
        </div>
        <p v-if="boarding.driver_arrived" class="journey-alert">وصل السائق إلى نقطة تجمعك.</p>
        <p v-if="boarding.wrong_bus" class="journey-alert journey-alert--danger">أنت عند حافلة مختلفة. راجع رقم الرحلة قبل التأكيد.</p>
        <div class="journey-actions">
          <Button
            variant="outline"
            :disabled="!canWait"
            :loading="busy === 'wait'"
            @click="run('wait', gateway.requestWait, 'وصل طلب الانتظار إلى السائق')"
          >انتظرني</Button>
          <Button
            theme="green"
            variant="solid"
            :disabled="!canConfirm"
            :loading="busy === 'boarded'"
            @click="run('boarded', gateway.claimBoarded, 'تم تسجيل صعودك')"
          >أنا في الحافلة</Button>
        </div>
        <small v-if="!canConfirm && boarding.status !== 'Boarded'">يتاح تأكيد الصعود عندما تصل الحافلة إلى نقطتك.</small>
      </article>

      <div class="journey-section">
        <div class="journey-section__title"><h3>الرحلات القادمة</h3><span>{{ trips.length }}</span></div>
        <article v-for="trip in trips" :key="trip.transport_request" class="journey-card">
          <div class="journey-card__main">
            <Badge :label="statusLabel(trip.boarding_window?.state || trip.trip_status)" />
            <h3>{{ trip.destination?.location || trip.destination?.stop_name || trip.pickup_point || 'رحلة مسار' }}</h3>
            <p>{{ trip.pickup_point || trip.my_pickup?.stop_name || 'نقطة التجمع' }}</p>
          </div>
          <dl class="journey-facts">
            <div><dt>الموعد</dt><dd><bdi>{{ dateTimeLabel(trip.pickup_datetime || trip.depart_time) || 'يحدد لاحقاً' }}</bdi></dd></div>
            <div><dt>الحافلة</dt><dd>{{ trip.vehicle?.plate_number || 'تحت الإسناد' }}</dd></div>
            <div><dt>السائق</dt><dd>{{ trip.driver?.full_name || 'تحت الإسناد' }}</dd></div>
          </dl>
          <div class="journey-actions">
            <a v-if="trip.maps_route_url" class="journey-link" :href="trip.maps_route_url" target="_blank" rel="noopener">عرض المسار</a>
            <Button variant="outline" :loading="busy === `pass:${trip.transport_request}`" @click="showPass(trip.transport_request)">بطاقة الصعود</Button>
          </div>
        </article>
      </div>

      <article v-if="pass" class="boarding-pass" aria-live="polite">
        <div><span class="journey-kicker">بطاقة الصعود</span><h3>{{ pass.destination_label || 'رحلة مسار' }}</h3><p>{{ pass.pickup_label }}</p></div>
        <img v-if="passImage" :src="passImage" alt="رمز بطاقة الصعود" />
      </article>

      <details v-if="pastTrips.length" class="journey-history">
        <summary>الرحلات السابقة <span>{{ pastTrips.length }}</span></summary>
        <article v-for="trip in pastTrips" :key="trip.transport_request" class="journey-history__row">
          <strong>{{ trip.destination?.location || trip.pickup_point || 'رحلة مسار' }}</strong>
          <bdi>{{ dateTimeLabel(trip.pickup_datetime) }}</bdi>
        </article>
      </details>
    </template>
  </section>
</template>
