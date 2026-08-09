<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <HomeSkeleton v-if="loading" :label="t('common.loading')" />

  <LoadError
    v-else-if="home.error"
    :title="t('errors.loadError')"
    :detail="homeErrorMessage"
    :hint="t('errors.retryHint')"
    :retry-label="t('common.retry')"
    @retry="reload"
  />

  <div v-else class="field-runway">
    <DecisionStage
      class="field-stage"
      :eyebrow="t('home.today')"
      :title="t('home.nextRide')"
      :subtitle="t('home.stepHint.' + step.key)"
    >
      <RideCard :ride="ride" :relative-hint="relativeHint" />

      <template #footer>
        <ActionDock>
          <template #primary>
            <Button
              class="dock-btn"
              variant="solid"
              theme="green"
              size="2xl"
              :label="t('home.step.' + step.key)"
              @click="go"
            >
              <template #prefix><Icon :name="step.icon" :size="20" /></template>
            </Button>
          </template>
        </ActionDock>
      </template>
    </DecisionStage>

    <aside class="field-evidence">
      <AttentionCard
        v-if="alerts.length"
        :alerts="alerts"
        :window-days="IQAMA_NOTIFY_HR_LEAD_DAYS"
        :notifying="notifyHr.loading"
        :notified="hrNotified"
        :error="notifyHrError"
        @notify="sendNotifyHr"
      />
      <BedCard :bed="bed" />
      <LoadError
        v-if="contacts.error"
        :title="t('contacts.title')"
        :detail="contactsErrorMessage"
        :hint="t('errors.retryHint')"
        :retry-label="t('common.retry')"
        @retry="contacts.reload()"
      />
      <ContactsCard v-else :contacts="contacts.data" />
    </aside>

    <DestinationsCard class="field-ledger" :open-requests="openRequests" />
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref } from "vue";
import { TRIP } from "@shared/statusVocabularies";
import { useRouter } from "vue-router";
import { Button, createResource } from "frappe-ui";
import ActionDock from "@shared/components/ActionDock.vue";
import DecisionStage from "@shared/components/DecisionStage.vue";
import HomeSkeleton from "../components/HomeSkeleton.vue";
import LoadError from "@shared/components/LoadError.vue";
import RideCard from "../components/RideCard.vue";
import AttentionCard from "../components/AttentionCard.vue";
import BedCard from "../components/BedCard.vue";
import ContactsCard from "../components/ContactsCard.vue";
import DestinationsCard from "../components/DestinationsCard.vue";
import Icon from "../components/Icon.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import { useWorkerRealtime } from "../realtime.js";

defineProps({
  ctx: { type: Object, default: null },
});

const { t } = useI18n();
const router = useRouter();

const home = createResource({
  url: "apex.salis.api.masar.get_worker_home",
  auto: true,
  onError: () => {},
});

const contacts = createResource({
  url: "apex.salis.api.masar.get_worker_contacts",
  auto: true,
  onError: () => {},
});

useWorkerRealtime(() => home.reload().catch(() => {}));

const loading = computed(() => home.loading && !home.data);
const homeErrorMessage = computed(() => resourceErrorMessage(home.error));
const contactsErrorMessage = computed(() => resourceErrorMessage(contacts.error));

function reload() {
  home.reload();
  contacts.reload();
}

const ride = computed(() => home.data?.next_ride || null);
const bed = computed(() => home.data?.bed || null);
const alerts = computed(() => home.data?.profile_alerts || []);
const openRequests = computed(() => home.data?.open_request_count || 0);

const now = ref(Date.now());
const timer = setInterval(() => (now.value = Date.now()), 60000);
onUnmounted(() => clearInterval(timer));

const relativeHint = computed(() => {
  const s = ride.value?.pickup_datetime;
  if (!s) return "";
  const m = String(s).match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);
  if (!m) return "";
  const today = new Date();
  const sameDay =
    today.getFullYear() === +m[1] && today.getMonth() === +m[2] - 1 && today.getDate() === +m[3];
  if (!sameDay) return "";
  if (m[4] == null) return t("home.today");
  const at = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]).getTime();
  const diffMin = Math.round((at - now.value) / 60000);
  if (diffMin < 0) return "";
  if (diffMin === 0) return t("home.now");
  if (diffMin < 60) return t("home.inM", { m: diffMin });
  return t("home.inHm", { h: Math.floor(diffMin / 60), m: diffMin % 60 });
});

const step = computed(() => {
  const r = ride.value;
  if (!r) return { key: "requestRide", icon: "plus", to: "/request-transport" };
  if (r.trip_status === TRIP.DISPATCHED) return { key: "openRide", icon: "badge", to: "/transport" };
  return { key: "viewRide", icon: "route", to: "/transport" };
});

function go() {
  router.push(step.value.to);
}

const IQAMA_NOTIFY_HR_LEAD_DAYS = 30;

const hrNotified = ref(false);
const notifyHrError = ref("");
const notifyHr = createResource({
  url: "apex.salis.api.masar.notify_hr_iqama_expiring",
  onSuccess: (data) => {
    hrNotified.value = !!(data && data.notified);
    notifyHrError.value = hrNotified.value ? "" : t("home.notifyHrFailed");
    if (!hrNotified.value) home.reload();
  },
  onError: (e) => {
    notifyHrError.value = resourceErrorMessage(e, "home.notifyHrFailed");
  },
});

function sendNotifyHr() {
  notifyHrError.value = "";
  notifyHr.submit({});
}
</script>
