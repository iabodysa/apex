<script setup>
import { computed, inject, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { Badge, Button, ErrorMessage, createResource, toast } from "frappe-ui";
import QRCode from "qrcode";
import { dateTimeLabel, remainingSeconds } from "../../core/displayLabels.js";
import PortalSkeleton from "../../components/PortalSkeleton.vue";
import PortalErrorState from "../../components/PortalErrorState.vue";

const gateway = inject("workerGateway");
const subscribe = inject("portalSubscribe", () => () => {});
const transportResource = createResource({
  url: "apex.salis.api.masar.get_worker_transport",
  method: "GET",
  auto: false,
});
const boardingResource = createResource({
  url: "apex.salis.api.boarding_flow.worker_trip_boarding",
  method: "GET",
  auto: false,
});
const contextResource = createResource({
  url: "apex.salis.api.masar.get_worker_context",
  method: "GET",
  auto: false,
});
const boardingPassResource = createResource({
  url: "apex.salis.api.masar.get_worker_boarding_pass",
  method: "GET",
  auto: false,
});
const ratingResource = createResource({
  url: "apex.salis.api.masar.submit_trip_rating",
  method: "POST",
  auto: false,
});
const state = ref("loading");
const transport = ref({ upcoming: [], past: [] });
const boarding = ref(null);
const error = ref("");
const busy = ref("");
const pass = ref(null);
const passImage = ref("");
const now = ref(Date.now());
const ratingDrafts = reactive({});
const ratingMessages = reactive({});
let pollTimer;
let clockTimer;
let activeRoom = "";
let unsubscribers = [];

const trips = computed(() => transport.value?.upcoming || []);
const pastTrips = computed(() => transport.value?.past || []);
const hasContent = computed(() => trips.value.length || pastTrips.value.length || boarding.value?.dispatch_trip);
const canWait = computed(() => boarding.value?.dispatch_trip && !["Boarded", "Absent"].includes(boarding.value.status) && Number(boarding.value.wait_count || 0) < Number(boarding.value.wait_max || 0));
const canConfirm = computed(() => boarding.value?.boarding_window?.can_confirm && boarding.value.status !== "Boarded");
const waitSeconds = computed(() => remainingSeconds(boarding.value?.wait_at, boarding.value?.wait_window_seconds, now.value));
const notifySeconds = computed(() => remainingSeconds(boarding.value?.notify_at, boarding.value?.notify_window_seconds, now.value));

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

function ratingDraft(trip) {
  if (!ratingDrafts[trip.dispatch_trip]) {
    ratingDrafts[trip.dispatch_trip] = { rating: 0, feedback: "" };
  }
  return ratingDrafts[trip.dispatch_trip];
}

async function rateTrip(trip) {
  const draft = ratingDraft(trip);
  if (!draft.rating) return;
  const key = `rating:${trip.dispatch_trip}`;
  busy.value = key;
  error.value = "";
  try {
    await ratingResource.submit({
      dispatch_trip: trip.dispatch_trip,
      rating: draft.rating,
      feedback: draft.feedback,
    });
    trip.has_rated = true;
    ratingMessages[trip.dispatch_trip] = "تم إرسال تقييمك، شكراً لك.";
  } catch (reason) {
    error.value = reason?.message || "تعذّر إرسال التقييم.";
  } finally {
    busy.value = "";
  }
}

function stopLive() {
  clearInterval(pollTimer);
  clearInterval(clockTimer);
  pollTimer = undefined;
  clockTimer = undefined;
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
    const [transportData, boardingData, context] = await Promise.all([transportResource.fetch(), boardingResource.fetch(), contextResource.fetch()]);
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
    toast.create({ type: "success", message });
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
    const result = await boardingPassResource.fetch({ transport_request: request });
    pass.value = result?.pass || null;
    passImage.value = pass.value?.qr_payload ? await QRCode.toDataURL(pass.value.qr_payload, { margin: 1, width: 320 }) : "";
  } catch (reason) {
    error.value = reason?.message || "تعذّر عرض بطاقة الصعود.";
  } finally {
    busy.value = "";
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
  <section class="feature-page journey-page" :aria-busy="state === 'loading'">
    <header class="feature-page__heading journey-heading">
      <div>
        <p class="feature-page__eyebrow">رحلات مسار</p>
        <h2>رحلتك من الباب إلى المقعد</h2>
        <p>تابع وصول الحافلة، اطلب من السائق الانتظار، ثم أكد صعودك.</p>
      </div>
    </header>

    <PortalSkeleton v-if="state === 'loading'" :rows="2" label="جارٍ تحميل الرحلة" />
    <PortalErrorState v-else-if="state === 'denied'" title="تعذّر فتح الرحلات" message="هذا القسم غير متاح لحسابك." @retry="load()" />
    <PortalErrorState v-else-if="state === 'error'" title="تعذّر تحميل الرحلات" :message="error" @retry="load()" />
    <div v-else-if="state === 'empty'" class="feature-state">
      <strong>يومك هادئ</strong>
      <p>لا توجد رحلة مجدولة لك حالياً.</p>
    </div>

    <template v-else>
      <ErrorMessage v-if="error" :message="error" />
      <article v-if="boarding?.dispatch_trip" class="journey-live" aria-live="polite">
        <div class="journey-live__top">
          <div>
            <span class="journey-kicker">الحالة الآن</span>
            <h3>
              {{ statusLabel(boarding.boarding_window?.state || boarding.status) }}
            </h3>
          </div>
          <Badge :label="statusLabel(boarding.status)" />
        </div>
        <p v-if="boarding.driver_arrived" class="journey-alert">وصل السائق إلى نقطة تجمعك.</p>
        <p v-if="notifySeconds !== null" class="journey-alert journey-alert--notice">
          {{ notifySeconds > 0 ? `السائق نبهك، موعد المغادرة خلال ${notifySeconds} ثانية.` : "الحافلة تستعد للمغادرة الآن." }}
        </p>
        <p v-if="boarding.wrong_bus" class="journey-alert journey-alert--danger">أنت عند حافلة مختلفة. راجع رقم الرحلة قبل التأكيد.</p>
        <div class="journey-actions">
          <Button variant="outline" :disabled="!canWait" :loading="busy === 'wait'" @click="run('wait', gateway.requestWait, 'وصل طلب الانتظار إلى السائق')">انتظرني</Button>
          <Button theme="green" variant="solid" :disabled="!canConfirm" :loading="busy === 'boarded'" @click="run('boarded', gateway.claimBoarded, 'تم تسجيل صعودك')">أنا في الحافلة</Button>
        </div>
        <small v-if="boarding.wait_max" class="journey-wait-note">
          طلب الانتظار {{ boarding.wait_count || 0 }} من {{ boarding.wait_max }}
          <template v-if="waitSeconds">· طلبك فعال لمدة {{ waitSeconds }} ثانية</template>
        </small>
        <small v-if="!canConfirm && boarding.status !== 'Boarded'">يتاح تأكيد الصعود عندما تصل الحافلة إلى نقطتك.</small>
      </article>

      <div class="journey-section">
        <div class="journey-section__title">
          <h3>الرحلات القادمة</h3>
          <span>{{ trips.length }}</span>
        </div>
        <article v-for="trip in trips" :key="trip.transport_request" class="journey-card">
          <div class="journey-card__main">
            <Badge :label="statusLabel(trip.boarding_window?.state || trip.trip_status)" />
            <h3>
              {{ trip.destination?.location || trip.destination?.stop_name || trip.pickup_point || "رحلة مسار" }}
            </h3>
            <p>
              {{ trip.pickup_point || trip.my_pickup?.stop_name || "نقطة التجمع" }}
            </p>
          </div>
          <dl class="journey-facts">
            <div>
              <dt>الموعد</dt>
              <dd>
                <bdi>{{ dateTimeLabel(trip.pickup_datetime || trip.depart_time) || "يحدد لاحقاً" }}</bdi>
              </dd>
            </div>
            <div>
              <dt>الحافلة</dt>
              <dd>{{ trip.vehicle?.plate_number || "تحت الإسناد" }}</dd>
            </div>
            <div>
              <dt>السائق</dt>
              <dd>{{ trip.driver?.full_name || "تحت الإسناد" }}</dd>
            </div>
          </dl>
          <div class="journey-actions">
            <a v-if="trip.maps_route_url" class="journey-link" :href="trip.maps_route_url" target="_blank" rel="noopener">عرض المسار</a>
            <Button variant="outline" :loading="busy === `pass:${trip.transport_request}`" @click="showPass(trip.transport_request)">بطاقة الصعود</Button>
          </div>
        </article>
      </div>

      <article v-if="pass" class="boarding-pass" aria-live="polite">
        <div>
          <span class="journey-kicker">بطاقة الصعود</span>
          <h3>{{ pass.destination_label || "رحلة مسار" }}</h3>
          <p>{{ pass.pickup_label }}</p>
        </div>
        <img v-if="passImage" :src="passImage" alt="رمز بطاقة الصعود" />
      </article>

      <details v-if="pastTrips.length" class="journey-history">
        <summary>
          الرحلات السابقة
          <span>{{ pastTrips.length }}</span>
        </summary>
        <article v-for="trip in pastTrips" :key="trip.transport_request" class="journey-history__row">
          <div>
            <strong>{{ trip.destination?.location || trip.pickup_point || "رحلة مسار" }}</strong>
            <bdi>{{ dateTimeLabel(trip.pickup_datetime) }}</bdi>
          </div>
          <form
            v-if="trip.dispatch_trip && trip.trip_status === 'Completed' && !trip.has_rated"
            class="journey-rating"
            @submit.prevent="rateTrip(trip)"
          >
            <fieldset>
              <legend>قيّم الرحلة</legend>
              <div class="journey-rating__stars">
                <button
                  v-for="score in 5"
                  :key="score"
                  type="button"
                  :aria-label="`${score} نجوم`"
                  :aria-pressed="ratingDraft(trip).rating === score"
                  @click="ratingDraft(trip).rating = score"
                >★</button>
              </div>
            </fieldset>
            <label>
              ملاحظات اختيارية
              <textarea
                v-model="ratingDraft(trip).feedback"
                :data-rating-feedback="trip.dispatch_trip"
                maxlength="2000"
                rows="2"
              />
            </label>
            <Button
              type="button"
              variant="outline"
              :disabled="!ratingDraft(trip).rating"
              :loading="busy === `rating:${trip.dispatch_trip}`"
              :data-rating-submit="trip.dispatch_trip"
              @click="rateTrip(trip)"
            >إرسال التقييم</Button>
          </form>
          <p v-else-if="trip.has_rated || ratingMessages[trip.dispatch_trip]" class="journey-rating__thanks" role="status">
            {{ ratingMessages[trip.dispatch_trip] || "تم إرسال تقييمك مسبقاً." }}
          </p>
        </article>
      </details>
    </template>
  </section>
</template>
