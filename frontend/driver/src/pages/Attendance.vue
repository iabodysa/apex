<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="space-y-5">
    <LoadingState v-if="today.loading && !state.exists" :label="t('common.loading')" />

    <LoadError
      v-else-if="today.error"
      :title="t('errors.loadFailed')"
      :detail="err"
      :hint="t('errors.retryHint')"
      :retry-label="t('common.retry')"
      @retry="today.reload()"
    />

    <template v-else>
    <Panel :title="t('attendance.today')">
      <template #status>
        <StatusLabel :label="statusLabel" :tone="stateTone" />
      </template>

      <p class="state-line">{{ stateLabel }}</p>

      <div v-if="state.exists" class="divider my-4"></div>

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
    </Panel>

    <section class="card card-pad space-y-3">
      <p class="text-sm text-soft">{{ t("attendance.hint") }}</p>

      <div v-if="!state.checked_out">
        <label class="field-label" for="att-photo">{{ t("attendance.photo") }}</label>
        <input
          ref="photoInput"
          id="att-photo"
          type="file"
          :accept="PHOTO_ACCEPT"
          capture="environment"
          class="visually-hidden"
          :disabled="loading || uploading"
          @change="onPhoto"
        />
        <Button
          variant="outline"
          size="xl"
          :disabled="loading || uploading"
          :loading="uploading"
          :label="photoName || t('attendance.photo')"
          @click="choosePhoto"
        >
          <template #prefix><Icon name="image" :size="18" /></template>
        </Button>
        <p v-if="uploading" class="mt-1 text-xs text-muted">{{ t("common.loading") }}</p>
        <p v-else-if="photoError" class="mt-1 text-xs text-danger">{{ photoError }}</p>
        <p v-else-if="photoName" class="mt-1 text-xs text-success">
          {{ t("attendance.photoAttached") }}: {{ photoName }}
        </p>
      </div>

      <p v-if="state.checked_out" class="status-note status-ok">{{ t("attendance.doneForToday") }}</p>
    </section>

    <Panel :title="t('attendance.history')">
      <Skeleton v-if="history.loading" :rows="3" />
      <LoadError
        v-else-if="history.error"
        :title="t('attendance.historyFailed')"
        :detail="historyErrorMessage"
        :hint="t('errors.retryHint')"
        :retry-label="t('common.retry')"
        @retry="history.reload()"
      />
      <EmptyState v-else-if="!rows.length" :title="t('attendance.historyEmpty')">
        <template #icon><Icon name="calendar" :size="22" /></template>
      </EmptyState>
      <ul v-else class="space-y-3">
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
            <StatusLabel class="ms-auto shrink-0" :label="rowStatusLabel(row.status)" :tone="rowTone(row.status)" />
          </div>
          <div v-if="i < rows.length - 1" class="divider mt-3"></div>
        </li>
      </ul>
    </Panel>

    <ActionDock>
      <template #secondary>
        <Button
          class="dock-btn"
          variant="outline"
          size="2xl"
          :disabled="loading || uploading || today.loading || !state.checked_in || state.checked_out"
          :loading="checkout.loading"
          :label="state.checked_out ? t('attendance.checkedOutLabel') : t('attendance.checkOut')"
          @click="doCheckOut()"
        >
          <template #prefix><Icon name="calendar" :size="20" /></template>
        </Button>
      </template>
      <template #primary>
        <Button
          class="dock-btn"
          variant="solid"
          theme="green"
          size="2xl"
          :disabled="loading || uploading || today.loading || state.checked_in"
          :loading="checkin.loading"
          :label="state.checked_in ? t('attendance.checkedInLabel') : t('attendance.checkIn')"
          @click="doCheckIn()"
        >
          <template #prefix><Icon name="calendar" :size="20" /></template>
        </Button>
      </template>
    </ActionDock>
    </template>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { ATTENDANCE } from "@shared/statusVocabularies";
import { Button, createResource } from "frappe-ui";
import ActionDock from "@shared/components/ActionDock.vue";
import EmptyState from "@shared/components/EmptyState.vue";
import LoadError from "@shared/components/LoadError.vue";
import Panel from "@shared/components/Panel.vue";
import StatusLabel from "@shared/components/StatusLabel.vue";
import Icon from "../components/Icon.vue";
import LoadingState from "../components/LoadingState.vue";
import Skeleton from "../components/Skeleton.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import { pushToast } from "../toast";
import { readPhotoFile, UnsupportedPhotoType } from "../upload";
import { PHOTO_ACCEPT } from "@shared/photoFile.js";

const { t, fmtTime } = useI18n();

const err = ref("");
const loading = ref(false);

const photo = ref({ photo: null, photo_filename: null });
const photoName = ref("");
const photoError = ref("");
const uploading = ref(false);
const photoInput = ref(null);

function choosePhoto() {
  photoInput.value?.click();
}

async function onPhoto(e) {
  const file = e.target.files && e.target.files[0];
  e.target.value = "";
  if (!file) return;
  uploading.value = true;
  photoError.value = "";
  try {
    photo.value = await readPhotoFile(file);
    photoName.value = photo.value.photo ? file.name : "";
  } catch (failure) {
    clearPhoto();
    photoError.value =
      failure instanceof UnsupportedPhotoType ? t("attendance.photoType") : t("common.error");
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

const today = createResource({
  url: "apex.salis.api.driver_portal.get_today_attendance",
  auto: true,
  onSuccess: (r) => apply(r),
  onError: (e) => { err.value = e.messages?.[0] || t("errors.loadFailed"); },
});

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

const stateLabel = computed(() => {
  if (state.checked_out && state.check_out) return t("attendance.checkedOutAt", { time: fmtTime(state.check_out) });
  if (state.checked_in && state.check_in) return t("attendance.checkedInAt", { time: fmtTime(state.check_in) });
  return t("attendance.notCheckedIn");
});

function rowStatusLabel(status) {
  switch (status) {
    case ATTENDANCE.PRESENT: return t("attendance.statusPresent");
    case ATTENDANCE.LATE: return t("attendance.statusLate");
    case ATTENDANCE.ABSENT: return t("attendance.statusAbsent");
    case ATTENDANCE.ON_LEAVE: return t("attendance.statusOnLeave");
    default: return t("common.none");
  }
}
function rowTone(status) {
  if (status === ATTENDANCE.ABSENT) return "danger";
  if (status === ATTENDANCE.LATE) return "warning";
  if (status === ATTENDANCE.ON_LEAVE) return "neutral";
  return "success";
}

const statusLabel = computed(() =>
  state.status ? rowStatusLabel(state.status) : (state.checked_in ? t("attendance.statusPresent") : t("common.none"))
);
const stateTone = computed(() => {
  if (state.status) return rowTone(state.status);
  return state.checked_in ? "success" : "neutral";
});

const history = createResource({
  url: "apex.salis.api.driver_portal.my_attendance",
  auto: true,
});
const rows = computed(() => history.data?.rows ?? []);
const historyErrorMessage = computed(() =>
  resourceErrorMessage(history.error, "attendance.historyFailed"),
);

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

<style scoped>
.state-line {
  color: var(--c-ink);
  font-size: var(--fs-h3);
  font-weight: var(--fw-heading);
  line-height: 1.3;
}
</style>
