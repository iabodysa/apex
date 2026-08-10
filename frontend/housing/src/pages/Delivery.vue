<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <ListSkeleton
    v-if="deliveriesRes.loading && !deliveries.length"
    :rows="5"
    :label="t('delivery.loadingLabel')"
  />

  <LoadError
    v-else-if="deliveriesRes.error"
    :title="t('errors.deliveriesFailed')"
    :detail="loadErrorMessage"
    :hint="t('errors.retryHint')"
    :retry-label="t('common.retry')"
    @retry="reloadDeliveries()"
  />

  <EmptyState
    v-else-if="!deliveries.length"
    :title="t('delivery.emptyTitle')"
    :hint="t('delivery.emptySubtitle')"
  >
    <template #icon><Icon name="check-circle" :size="24" /></template>
    <template #action>
      <Button size="xl" variant="outline" :label="t('common.refresh')" @click="reloadDeliveries()" />
    </template>
  </EmptyState>

  <template v-else>
    <div class="hz-split">
      <div class="hz-split-list">
        <div class="list-head">
          <h2 class="list-title">{{ t("delivery.listTitle") }}</h2>
          <Badge theme="orange" size="lg" :label="t('delivery.count', { n: deliveryCount })" />
          <Badge
            v-if="hasMoreThanShown"
            theme="gray"
            size="lg"
            :label="t('delivery.showingOldest', { n: deliveries.length })"
          />
        </div>

        <DeliveryRow
          v-for="del in deliveries"
          :key="del.name"
          :delivery="del"
          :open="selected === del.name"
          @open="openDelivery(del.name)"
        />
      </div>

      <aside v-if="desktop" class="hz-split-detail">
        <div v-if="selectedDelivery" class="pane">
          <DeliveryDetail :delivery="selectedDelivery" :error="actionError" />
        </div>
        <div v-else class="pane pane-idle">
          <EmptyState :title="t('delivery.pickTitle')" :hint="t('delivery.pickHint')">
            <template #icon><Icon name="truck" :size="24" /></template>
          </EmptyState>
        </div>
      </aside>
    </div>

    <div v-if="selectedDelivery && desktop" class="hz-dock">
      <Button
        v-if="selectedDelivery.status === 'Pending Exits'"
        class="dock-btn"
        size="2xl"
        variant="solid"
        theme="green"
        :disabled="!mayClearNext"
        :loading="busy === selectedDelivery.name"
        :loading-text="t('delivery.clearing')"
        :label="t('delivery.clearCheckpoint', { label: exitLabel(nextExit(selectedDelivery)) })"
        @click="confirmOpen = true"
      >
        <template #prefix><Icon name="shield-check" :size="20" /></template>
      </Button>
      <!-- Disabled with the reason beside it, per DESIGN.md §7 — the control stays visible
           so the reader learns WHO clears this checkpoint rather than meeting a refusal. -->
      <p v-if="selectedDelivery.status === 'Pending Exits' && !mayClearNext" class="dock-hint">
        {{ t("delivery.notYourCheckpoint", { label: exitLabel(nextExit(selectedDelivery)) }) }}
      </p>

      <template v-else>
        <Button
          class="dock-btn"
          size="2xl"
          variant="solid"
          theme="green"
          :label="t('delivery.confirmReceipt')"
          @click="openOtp"
        >
          <template #prefix><Icon name="key" :size="20" /></template>
        </Button>
        <Button
          class="dock-btn dock-btn-second"
          size="xl"
          variant="outline"
          :loading="busy === selectedDelivery.name"
          :label="t('delivery.showCode')"
          @click="showCode"
        >
          <template #prefix><Icon name="qr" :size="18" /></template>
        </Button>
      </template>

      <p class="dock-hint">{{ stepHint }}</p>
    </div>

    <Dialog
      v-if="!desktop"
      :modelValue="!!selectedDelivery"
      :options="{ title: selectedTitle, size: 'lg' }"
      @update:modelValue="(open) => !open && closeDelivery()"
    >
      <template #body-content>
        <DeliveryDetail
          v-if="selectedDelivery"
          :delivery="selectedDelivery"
          :error="actionError"
          :heading="false"
        />
      </template>
      <template #actions>
        <div class="sheet-actions">
          <Button
            class="dock-btn"
            size="2xl"
            variant="solid"
            theme="green"
            :disabled="selectedDelivery.status === 'Pending Exits' && !mayClearNext"
            :loading="busy === selectedDelivery.name"
            :loading-text="selectedDelivery.status === 'Pending Exits' ? t('delivery.clearing') : t('delivery.confirming')"
            :label="
              selectedDelivery.status === 'Pending Exits'
                ? t('delivery.clearCheckpoint', { label: exitLabel(nextExit(selectedDelivery)) })
                : t('delivery.confirmReceipt')
            "
            @click="selectedDelivery.status === 'Pending Exits' ? (confirmOpen = true) : openOtp()"
          />
          <Button
            v-if="selectedDelivery.status !== 'Pending Exits'"
            size="xl"
            variant="outline"
            :label="t('delivery.showCode')"
            @click="showCode"
          />
        </div>
      </template>
    </Dialog>

    <Dialog v-model="codeOpen" :options="{ title: t('delivery.codeTitle'), size: 'sm' }">
      <template #body-content>
        <div class="sheet">
          <p v-if="codeValue" class="code-value mono">{{ codeValue }}</p>
          <p class="sheet-text">{{ t("delivery.codeHint") }}</p>
          <ErrorMessage v-if="codeError" :message="codeError" />
        </div>
      </template>
      <template #actions>
        <Button size="2xl" variant="solid" :label="t('common.close')" @click="codeOpen = false" />
      </template>
    </Dialog>

    <Dialog
      v-model="confirmOpen"
      :options="{ title: t('delivery.confirmClearTitle'), size: 'sm' }"
    >
      <template #body-content>
        <p class="sheet-text">
          {{ t("delivery.confirmClearMessage", { label: exitLabel(nextExit(selectedDelivery || {})) }) }}
        </p>
      </template>
      <template #actions>
        <div class="sheet-actions">
          <Button
            size="2xl"
            variant="solid"
            theme="red"
            :loading="!!busy"
            :loading-text="t('delivery.clearing')"
            :label="t('delivery.clearCheckpoint', { label: exitLabel(nextExit(selectedDelivery || {})) })"
            @click="passExit"
          />
          <Button size="xl" variant="outline" :label="t('common.cancel')" @click="confirmOpen = false" />
        </div>
      </template>
    </Dialog>

    <Dialog v-model="otpOpen" :options="{ title: t('delivery.otpTitle'), size: 'sm' }">
      <template #body-content>
        <div class="sheet">
          <FormControl
            class="otp"
            type="text"
            size="lg"
            dir="ltr"
            inputmode="numeric"
            autocomplete="one-time-code"
            maxlength="6"
            placeholder="000000"
            :label="t('delivery.enterOtp')"
            :description="t('delivery.otpHint')"
            v-model="otpCode"
          />
          <ErrorMessage v-if="actionError" :message="actionError" />
        </div>
      </template>
      <template #actions>
        <div class="sheet-actions">
          <Button
            size="2xl"
            variant="solid"
            theme="green"
            :disabled="otpCode.length !== 6"
            :loading="!!busy"
            :loading-text="t('delivery.confirming')"
            :label="t('delivery.confirmReceipt')"
            @click="confirmReceipt"
          />
          <Button size="xl" variant="outline" :label="t('common.cancel')" @click="otpOpen = false" />
        </div>
      </template>
    </Dialog>
  </template>
</template>

<script setup>
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Badge, Button, Dialog, ErrorMessage, FormControl, createResource, toast } from "frappe-ui";
import { call } from "@shared/call";
import EmptyState from "@shared/components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import DeliveryRow from "../components/DeliveryRow.vue";
import DeliveryDetail from "../components/DeliveryDetail.vue";
import ListSkeleton from "@shared/components/ListSkeleton.vue";
import LoadError from "../components/LoadError.vue";
import { useI18n, apiErrorMessage, resourceErrorMessage } from "../i18n";
import { useDesktop } from "@shared/useBreakpoint.js";
import { nextExit } from "../gates";
import { canClearExit } from "../portal.js";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const desktop = useDesktop();

const API = "apex.habitat.api.facility_asset_delivery.";
const EXIT_METHOD = { 1: API + "pass_exit_1", 2: API + "pass_exit_2", 3: API + "pass_exit_3" };

const busy = ref("");
const actionError = ref("");
const confirmOpen = ref(false);
const otpOpen = ref(false);
const otpCode = ref("");
const codeOpen = ref(false);
const codeValue = ref("");
const codeError = ref("");

const PENDING_FILTERS = [["status", "in", ["Pending Exits", "Released"]]];
const PAGE_LENGTH = 200;

const deliveriesRes = createResource({
  url: "frappe.client.get_list",
  params: {
    doctype: "Facility Asset Delivery",
    filters: PENDING_FILTERS,
    fields: [
      "name",
      "status",
      "from_building",
      "to_building",
      "asset_serial_number",
      "exit1_security_cleared",
      "exit2_logistics_cleared",
      "exit3_receiving_cleared",
    ],
    order_by: "creation asc",
    limit_page_length: PAGE_LENGTH,
  },
  auto: true,
});

const deliveries = computed(() => deliveriesRes.data || []);
const deliveryCount = computed(() => deliveries.value.length);
const hasMoreThanShown = computed(() => deliveries.value.length >= PAGE_LENGTH);

function reloadDeliveries() {
  return deliveriesRes.reload();
}
const loadErrorMessage = computed(() =>
  resourceErrorMessage(deliveriesRes.error, "errors.deliveriesFailed"),
);

const selected = computed(() => route.params.name || "");
const selectedDelivery = computed(() => deliveries.value.find((d) => d.name === selected.value) || null);
const mayClearNext = computed(() => {
  const del = selectedDelivery.value;
  return !!del && canClearExit(nextExit(del));
});

function openDelivery(name) {
  actionError.value = "";
  router.push({ path: "/delivery/" + encodeURIComponent(name) });
}
function closeDelivery() {
  router.push({ path: "/delivery" });
}

const selectedTitle = computed(() => {
  const del = selectedDelivery.value;
  if (!del) return "";
  return del.asset_serial_number || del.name;
});

const stepHint = computed(() => {
  const del = selectedDelivery.value;
  if (!del) return "";
  const n = nextExit(del);
  return n ? t("delivery.exitStep", { n }) : t("delivery.allCleared");
});

function exitLabel(n) {
  return n ? t("delivery.exit" + n) : "";
}

function openOtp() {
  otpCode.value = "";
  actionError.value = "";
  otpOpen.value = true;
}

async function showCode() {
  const del = selectedDelivery.value;
  if (!del || busy.value) return;
  busy.value = del.name;
  codeValue.value = "";
  codeError.value = "";
  codeOpen.value = true;
  try {
    const code = await call(API + "regenerate_code", {
      args: { delivery: del.name },
      type: "POST",
    });
    codeValue.value = String(code || "");
  } catch (err) {
    codeError.value = apiErrorMessage(err, "delivery.codeDenied");
  } finally {
    busy.value = "";
  }
}

async function passExit() {
  const del = selectedDelivery.value;
  if (!del) return;
  const n = nextExit(del);
  if (!n || busy.value) return;
  busy.value = del.name;
  actionError.value = "";
  try {
    await call(EXIT_METHOD[n], { args: { delivery: del.name }, type: "POST" });
    confirmOpen.value = false;
    toast.create({ type: "success", message: t("delivery.exitCleared") });
    await reloadDeliveries();
  } catch (err) {
    actionError.value = apiErrorMessage(err);
    confirmOpen.value = false;
  } finally {
    busy.value = "";
  }
}

async function confirmReceipt() {
  const del = selectedDelivery.value;
  if (!del || otpCode.value.length !== 6 || busy.value) return;
  busy.value = del.name;
  actionError.value = "";
  try {
    await call(API + "confirm_receipt", {
      args: { delivery: del.name, code: otpCode.value },
      type: "POST",
    });
    otpOpen.value = false;
    otpCode.value = "";
    toast.create({ type: "success", message: t("delivery.confirmed") });
    closeDelivery();
    await reloadDeliveries();
  } catch (err) {
    actionError.value = apiErrorMessage(err);
  } finally {
    busy.value = "";
  }
}
</script>

<style scoped>
.list-head {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding-inline: var(--sp-1);
}
.list-title {
  flex: 1;
  min-inline-size: 0;
  font-size: var(--fs-h3);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
}

.dock-hint {
  margin-top: var(--sp-2);
  text-align: center;
  font-size: var(--fs-sm);
  color: var(--c-muted);
}

.sheet {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.sheet-text {
  font-size: var(--fs-body);
  line-height: 1.6;
  color: var(--c-ink-soft);
}
.sheet-actions {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.dock-btn-second {
  margin-top: var(--sp-2);
}
.code-value {
  direction: ltr;
  unicode-bidi: isolate;
  text-align: center;
  font-size: var(--fs-display, 2rem);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
}
</style>
