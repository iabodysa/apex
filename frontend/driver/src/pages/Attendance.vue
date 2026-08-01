<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <div class="space-y-5">
    <h2 class="section-title">{{ t("attendance.title") }}</h2>

    <!-- Initial load: spinner until the first state arrives. -->
    <LoadingState v-if="today.loading && !state.exists" :label="t('common.loading')" />

    <!-- Load failure: an explicit, retryable error state for the on-load fetch. -->
    <ErrorState v-else-if="today.error" :message="err || t('errors.loadFailed')" @retry="today.reload()" />

    <template v-else>
    <!-- Today's attendance state (fetched on load, updated reactively after each tap). -->
    <section class="card card-pad space-y-4">
      <div class="flex items-center justify-between gap-3">
        <div class="min-w-0">
          <p class="text-xs font-semibold uppercase tracking-wider text-soft">{{ t("attendance.today") }}</p>
          <p class="text-lg font-extrabold leading-tight">{{ stateLabel }}</p>
        </div>
        <span class="pill" :class="statePill">{{ statusLabel }}</span>
      </div>

      <div v-if="state.exists" class="divider"></div>

      <div v-if="state.exists" class="space-y-3 text-sm">
        <div v-if="state.check_in" class="flex items-center gap-2">
          <Icon name="calendar" :size="18" class="text-primary shrink-0" />
          <span class="text-muted">{{ t("attendance.checkedInLabel") }}</span>
          <span class="ms-auto font-semibold">{{ fmtTime(state.check_in) }}</span>
        </div>
        <div v-if="state.check_out" class="flex items-center gap-2">
          <Icon name="calendar" :size="18" class="text-primary shrink-0" />
          <span class="text-muted">{{ t("attendance.checkedOutLabel") }}</span>
          <span class="ms-auto font-semibold">{{ fmtTime(state.check_out) }}</span>
        </div>
        <div v-if="hoursPresent !== null" class="flex items-center gap-2">
          <Icon name="badge" :size="18" class="text-primary shrink-0" />
          <span class="text-muted">{{ t("attendance.hoursPresent") }}</span>
          <span class="ms-auto font-semibold">{{ hoursPresent }}</span>
        </div>
      </div>
    </section>

    <!-- Actions: each button reflects the current state — no blind re-submit. -->
    <section class="card card-pad space-y-3">
      <p class="text-sm text-soft">{{ t("attendance.hint") }}</p>

      <!-- Optional shift photo: read locally and attached by the attendance POST.
           Hidden once the shift is done. -->
      <div v-if="!state.checked_out">
        <label class="field-label" for="att-photo">{{ t("attendance.photo") }}</label>
        <input
          id="att-photo"
          type="file"
          :accept="PHOTO_ACCEPT"
          capture="environment"
          class="input"
          :disabled="loading || uploading"
          @change="onPhoto"
        />
        <p v-if="uploading" class="mt-1 text-xs text-muted">{{ t("common.loading") }}</p>
        <p v-else-if="photoError" class="mt-1 text-xs text-danger">{{ photoError }}</p>
        <p v-else-if="photoName" class="mt-1 text-xs text-success">
          {{ t("attendance.photoAttached") }}: {{ photoName }}
        </p>
      </div>

      <button
        class="btn btn-primary"
        :disabled="loading || uploading || today.loading || state.checked_in"
        @click="doCheckIn()"
      >
        <Icon name="calendar" :size="20" />
        {{ state.checked_in ? t("attendance.checkedInLabel") : t("attendance.checkIn") }}
      </button>
      <button
        class="btn btn-dark"
        :disabled="loading || uploading || today.loading || !state.checked_in || state.checked_out"
        @click="doCheckOut()"
      >
        <Icon name="calendar" :size="20" />
        {{ state.checked_out ? t("attendance.checkedOutLabel") : t("attendance.checkOut") }}
      </button>
      <p v-if="state.checked_out" class="status-note status-ok">{{ t("attendance.doneForToday") }}</p>
    </section>
    <!-- doneForToday above is a persistent shift-state note, not transient feedback. -->


    <!-- This month's history: a compact day list with status pill + stamped times. -->
    <section class="card card-pad space-y-3">
      <p class="text-sm font-semibold text-soft">{{ t("attendance.history") }}</p>
      <Skeleton v-if="history.loading" :rows="3" />
      <p v-else-if="!rows.length" class="text-sm text-muted">{{ t("attendance.historyEmpty") }}</p>
      <ul class="space-y-3">
        <li v-for="(row, i) in rows" :key="row.name">
          <div class="flex items-center gap-3">
            <div class="min-w-0">
              <p class="text-sm font-semibold leading-tight">
                <bdi>{{ row.attendance_date }}</bdi>
              </p>
              <p class="text-xs text-muted">
                <bdi>{{ fmtTime(row.check_in) || t("attendance.noTime") }}</bdi>
                <span class="mx-1">·</span>
                <bdi>{{ fmtTime(row.check_out) || t("attendance.noTime") }}</bdi>
              </p>
            </div>
            <span class="pill ms-auto shrink-0" :class="rowPill(row.status)">{{ rowStatusLabel(row.status) }}</span>
          </div>
          <div v-if="i < rows.length - 1" class="divider mt-3"></div>
        </li>
      </ul>
    </section>
    </template>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { createResource } from "frappe-ui";
import Icon from "../components/Icon.vue";
import LoadingState from "../components/LoadingState.vue";
import Skeleton from "../components/Skeleton.vue";
import ErrorState from "../components/ErrorState.vue";
import { useI18n } from "../i18n";
import { pushToast } from "../toast";
import { readPhotoFile, UnsupportedPhotoType } from "../upload";
import { PHOTO_ACCEPT } from "@shared/photoFile.js";

const { t, fmtTime } = useI18n();

// On-load fetch error only; action feedback goes through transient toasts.
const err = ref("");
const loading = ref(false);

// Optional shift photo included in the next credential-scoped attendance POST.
const photo = ref({ photo: null, photo_filename: null });
const photoName = ref("");
const photoError = ref("");
const uploading = ref(false);

async function onPhoto(e) {
  const file = e.target.files && e.target.files[0];
  // Reset the input so re-picking the same file re-fires change after a refusal.
  e.target.value = "";
  if (!file) return;
  uploading.value = true;
  photoError.value = "";
  try {
    photo.value = await readPhotoFile(file);
    photoName.value = photo.value.photo ? file.name : "";
  } catch (err) {
    clearPhoto();
    // Name the accepted formats: the operator can only act on a refusal that says
    // what to pick instead.
    photoError.value =
      err instanceof UnsupportedPhotoType ? t("attendance.photoType") : t("common.error");
    pushToast(photoError.value, "err");
  } finally {
    uploading.value = false;
  }
}

function clearPhoto() {
  photo.value = { photo: null, photo_filename: null };
  photoName.value = "";
  photoError.value = "";
}

// Single reactive source of truth for today's attendance. Seeded by the
// on-load fetch, then mutated in place by each check-in/out response so the
// page reflects the new state immediately (reactive, no full reload).
const state = reactive({
  exists: false,
  checked_in: false,
  checked_out: false,
  status: null,
  check_in: null,
  check_out: null,
  worked_hours: null,
});

function apply(s) {
  if (!s) return;
  state.exists = !!s.exists;
  state.checked_in = !!s.checked_in;
  state.checked_out = !!s.checked_out;
  state.status = s.status ?? null;
  state.check_in = s.check_in ?? null;
  state.check_out = s.check_out ?? null;
  state.worked_hours = s.worked_hours ?? null;
}

// ON LOAD: fetch today's attendance state for the signed-in driver.
const today = createResource({
  url: "apex.salis.api.driver_portal.get_today_attendance",
  auto: true,
  onSuccess: (r) => apply(r),
  onError: (e) => { err.value = e.messages?.[0] || t("errors.loadFailed"); },
});

// In-flight guard: while either action is submitting, `loading` is true so BOTH
// buttons are disabled. Without it a stray double-tap on a phone could fire
// check-out the instant check-in's response enabled it, stamping check_out a few
// ms after check_in (a zero-length "full day"). The guard makes a single tap a
// single action; the backend also refuses a check_out at/before check_in.
const checkin = createResource({
  url: "apex.salis.api.driver_portal.driver_check_in",
  onSuccess: (r) => { apply(r); clearPhoto(); pushToast(t("attendance.checkInDone"), "ok"); history.reload(); },
  onError: (e) => { pushToast(e.messages?.[0] || t("common.error"), "err"); },
});
const checkout = createResource({
  url: "apex.salis.api.driver_portal.driver_check_out",
  onSuccess: (r) => { apply(r); clearPhoto(); pushToast(t("attendance.checkOutDone"), "ok"); history.reload(); },
  onError: (e) => { pushToast(e.messages?.[0] || t("common.error"), "err"); },
});

// Guarded submitters: set `loading` for the whole request so no second tap (on
// either button) can fire while one is in flight.
async function doCheckIn() {
  if (loading.value || uploading.value || state.checked_in) return;
  loading.value = true;
  try {
    await checkin.submit(photo.value);
  } finally {
    loading.value = false;
  }
}
async function doCheckOut() {
  // Only act on a real prior check-in, and never when already checked out.
  if (loading.value || uploading.value || !state.checked_in || state.checked_out) return;
  loading.value = true;
  try {
    await checkout.submit(photo.value);
  } finally {
    loading.value = false;
  }
}

function timeToMinutes(v) {
  const m = String(v || "").match(/(\d{1,2}):(\d{2})/);
  if (!m) return null;
  return parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
}

// Headline line: not checked in / checked in at HH:MM / checked out at HH:MM.
const stateLabel = computed(() => {
  if (state.checked_out && state.check_out) return t("attendance.checkedOutAt", { time: fmtTime(state.check_out) });
  if (state.checked_in && state.check_in) return t("attendance.checkedInAt", { time: fmtTime(state.check_in) });
  return t("attendance.notCheckedIn");
});

// Server attendance status -> localized label / pill colour. One source for both
// the today card and the month history list, so the two never drift.
function rowStatusLabel(status) {
  switch (status) {
    case "Present": return t("attendance.statusPresent");
    case "Late": return t("attendance.statusLate");
    case "Absent": return t("attendance.statusAbsent");
    case "On Leave": return t("attendance.statusOnLeave");
    default: return t("common.none");
  }
}
function rowPill(status) {
  if (status === "Absent") return "pill-danger";
  if (status === "Late") return "pill-warning";
  if (status === "On Leave") return "pill-neutral";
  return "pill-success";
}

// Today's headline status label/pill (falls back to the open-shift state).
const statusLabel = computed(() =>
  state.status ? rowStatusLabel(state.status) : (state.checked_in ? t("attendance.statusPresent") : t("common.none"))
);
const statePill = computed(() => {
  if (state.status) return rowPill(state.status);
  return state.checked_in ? "pill-success" : "pill-neutral";
});

// This month's attendance history for the signed-in driver (read, on load).
const history = createResource({
  url: "apex.salis.api.driver_portal.my_attendance",
  auto: true,
});
const rows = computed(() => history.data?.rows ?? []);

// Computed hours present. Prefer the server's worked_hours (set once both
// stamps exist); otherwise derive from check-in -> check-out, or check-in ->
// now while the shift is still open.
const hoursPresent = computed(() => {
  if (state.worked_hours != null && state.worked_hours !== 0) {
    return Number(state.worked_hours).toFixed(2);
  }
  const start = timeToMinutes(state.check_in);
  if (start == null) return null;
  let end = timeToMinutes(state.check_out);
  if (end == null) {
    const now = new Date();
    end = now.getHours() * 60 + now.getMinutes();
  }
  const mins = end - start;
  if (mins <= 0) return null;
  return (mins / 60).toFixed(2);
});
</script>
