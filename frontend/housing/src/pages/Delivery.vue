<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- On-site half of the Facility Asset Delivery 3-exit transfer lock (T-673): the
     mobile surface where a housing supervisor clears their exit checkpoint
     (pass_exit_1/2/3) and, once Released, confirms the on-site code (confirm_receipt).
     Every write goes through the shared @shared/call POST layer; the backend
     fail-closes on role + order, so this UI only surfaces the next pending step.

     Shares Count.vue's shell, header, state blocks and .btn/.pill vocabulary —
     the two screens are one product, so a supervisor moving between the tabs
     should not be able to tell which one built the chrome. -->
<template>
  <div class="app-shell">
    <!-- Header: dark forest bar with the brand arc supergraphic (identical to Count). -->
    <header class="app-header">
      <div class="hero-arc" aria-hidden="true">
        <svg viewBox="0 0 200 200" fill="none" preserveAspectRatio="xMidYMid meet">
          <path d="M70 10 A95 95 0 0 1 70 190" stroke="currentColor" stroke-width="26" stroke-linecap="round" fill="none" />
          <path d="M120 35 A70 70 0 0 1 120 165" stroke="currentColor" stroke-width="26" stroke-linecap="round" fill="none" opacity="0.6" />
        </svg>
      </div>
      <div class="header-inner">
        <div class="header-bar">
          <div v-if="showBrand" class="header-brand">
            <img v-if="brandLogo" :src="brandLogo" alt="AFMCO" class="header-logo" />
            <template v-else>
              <span class="header-mark"><Icon name="truck" :size="20" /></span>
              <span class="header-word">{{ t("common.appName") }}</span>
            </template>
          </div>
          <span v-else class="header-word">{{ t("common.appName") }}</span>
          <LangToggle variant="header" />
        </div>
        <div class="greeting-block">
          <p class="greeting-eyebrow">{{ t("delivery.eyebrow") }}</p>
          <h1 class="greeting-title">{{ t("delivery.title") }}</h1>
          <!-- Occupies Count's building-chip slot and carries the one number the
               supervisor opened this tab for. -->
          <span v-if="deliveries.length" class="waiting-chip">
            <Icon name="clipboard-check" :size="14" />
            {{ t("delivery.waiting", { n: deliveries.length }) }}
          </span>
        </div>
      </div>
    </header>

    <main class="app-main">
      <!-- Loading. -->
      <div v-if="deliveriesResource.loading" class="state-center">
        <div class="spinner mx-auto" data-motion="loop"></div>
        <p class="state-msg">{{ t("common.loading") }}</p>
      </div>

      <!-- Error + retry. -->
      <div v-else-if="deliveriesResource.error" class="state-center">
        <div class="state-icon state-icon-danger"><Icon name="triangle-alert" :size="24" /></div>
        <p class="state-title">{{ t("errors.loadFailed") }}</p>
        <p class="state-msg">{{ loadErrorMessage }}</p>
        <button class="btn btn-primary state-btn" @click="deliveriesResource.reload()">
          {{ t("common.retry") }}
        </button>
      </div>

      <!-- Empty: nothing awaiting this supervisor. -->
      <div v-else-if="!deliveries.length" class="empty">
        <div class="empty-burst">
          <div class="empty-ring"></div>
          <Icon name="check-circle" :size="44" />
        </div>
        <h2 class="empty-title">{{ t("delivery.emptyTitle") }}</h2>
        <p class="empty-sub">{{ t("delivery.emptySubtitle") }}</p>
        <button class="btn btn-outline empty-switch" @click="deliveriesResource.reload()">
          {{ t("common.refresh") }}
        </button>
      </div>

      <!-- The queue. -->
      <div v-else class="list">
        <div class="list-intro">
          <h2 class="section-title">{{ t("delivery.listTitle") }}</h2>
          <p class="list-sub">{{ t("delivery.subtitle") }}</p>
        </div>

        <article v-for="del in deliveries" :key="del.name" class="d-card">
          <div class="d-head">
            <div class="d-id">
              <p class="d-id-label">{{ t("delivery.asset") }}</p>
              <!-- A record id is a Latin token inside Arabic prose: isolate it so
                   its characters keep their order, and give it the numeric face. -->
              <bdi class="d-id-value mono">{{ del.asset_serial_number || del.name }}</bdi>
              <bdi v-if="del.asset_serial_number" class="d-id-sub mono">{{ del.name }}</bdi>
            </div>
            <span class="pill" :class="del.status === 'Released' ? 'pill-success' : 'pill-warning'">
              <Icon :name="del.status === 'Released' ? 'key' : 'truck'" :size="12" />
              {{ statusLabel(del.status) }}
            </span>
          </div>

          <div class="d-route">
            <div class="d-kv">
              <p class="d-kv-key">{{ t("delivery.from") }}</p>
              <p class="d-kv-val">{{ del.from_building || t("common.none") }}</p>
            </div>
            <div class="d-kv">
              <p class="d-kv-key">{{ t("delivery.to") }}</p>
              <p class="d-kv-val">{{ del.to_building || t("common.none") }}</p>
            </div>
          </div>

          <!-- The three exits are an ORDERED sequence and the order is what the
               supervisor needs, so the track names each gate instead of drawing
               three anonymous bars. An <ol> gives assistive tech that order for
               free; aria-current marks the gate he is standing at. -->
          <ol class="gate-track" :aria-label="t('delivery.trackLabel')">
            <li
              v-for="g in gates(del)"
              :key="g.n"
              class="gate"
              :class="`gate-${g.state}`"
              :aria-current="g.state === 'current' ? 'step' : undefined"
            >
              <span class="gate-bar"></span>
              <span class="gate-name">
                <Icon v-if="g.state === 'cleared'" name="check" :size="11" />{{ g.label }}
              </span>
              <span class="sr-only">{{ t("delivery.gate." + g.state) }}</span>
            </li>
          </ol>

          <!-- Pending Exits: clear the next checkpoint. -->
          <button
            v-if="del.status === 'Pending Exits'"
            class="btn btn-primary d-action"
            :disabled="busy === del.name"
            @click="passExit(del)"
          >
            <template v-if="busy === del.name">
              <span class="btn-spin" data-motion="loop"><Icon name="loader" :size="18" /></span>
              {{ t("delivery.clearing") }}
            </template>
            <template v-else>
              <Icon name="shield-check" :size="18" />
              {{ t("delivery.clearCheckpoint", { label: exitLabel(nextExit(del)) }) }}
            </template>
          </button>

          <!-- Released: confirm the on-site code. -->
          <template v-else-if="del.status === 'Released'">
            <div v-if="selectedDelivery === del.name" class="otp">
              <label class="otp-label" :for="`otp-${del.name}`">{{ t("delivery.enterOtp") }}</label>
              <!-- dir=ltr: a confirmation code is a Latin token and must keep its
                   character order whichever way the page reads. -->
              <input
                :id="`otp-${del.name}`"
                v-model="otpCode"
                class="otp-input mono"
                type="text"
                dir="ltr"
                inputmode="numeric"
                autocomplete="one-time-code"
                maxlength="6"
                pattern="[0-9]*"
                placeholder="000000"
              />
              <div class="otp-actions">
                <button
                  class="btn btn-primary"
                  :disabled="otpCode.length !== 6 || busy === del.name"
                  @click="confirmReceipt(del.name)"
                >
                  <template v-if="busy === del.name">
                    <span class="btn-spin" data-motion="loop"><Icon name="loader" :size="18" /></span>
                    {{ t("delivery.confirming") }}
                  </template>
                  <template v-else>
                    <Icon name="key" :size="16" />
                    {{ t("delivery.confirmReceipt") }}
                  </template>
                </button>
                <button class="btn btn-outline" @click="selectedDelivery = null">
                  {{ t("common.cancel") }}
                </button>
              </div>
            </div>

            <button v-else class="btn btn-outline d-action" @click="openConfirm(del.name)">
              <Icon name="key" :size="18" />
              {{ t("delivery.confirmReceipt") }}
            </button>
          </template>

          <p v-if="errorFor === del.name && actionError" class="status-note status-err d-error">
            {{ actionError }}
          </p>
        </article>
      </div>
    </main>

    <!-- Transient confirmation. -->
    <transition name="fade">
      <p v-if="toast" class="toast" role="status">
        <Icon name="check-circle" :size="16" />
        {{ toast }}
      </p>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed } from "vue";
import { createResource } from "frappe-ui";
import { call } from "@shared/call";
import LangToggle from "@shared/components/LangToggle.vue";
import { useI18n, resourceErrorMessage } from "../i18n";
import Icon from "../components/Icon.vue";

const { t } = useI18n();

// Branding flags projected by the page template (www/housing.html).
const showBrand = computed(() => window.portal_show_brand !== false);
const brandLogo = computed(() => window.portal_logo || "");

const API = "apex.habitat.api.facility_asset_delivery.";
const EXIT_METHOD = { 1: API + "pass_exit_1", 2: API + "pass_exit_2", 3: API + "pass_exit_3" };

const selectedDelivery = ref(null);
const otpCode = ref("");
const busy = ref(""); // name of the delivery currently being actioned
const actionError = ref("");
const errorFor = ref(""); // name the current actionError belongs to
const toast = ref("");

// Both live stages the on-site supervisor acts on: clearing exits while Pending
// Exits, then confirming the code once Released.
const deliveriesResource = createResource({
  url: "frappe.client.get_list",
  params: {
    doctype: "Facility Asset Delivery",
    filters: [["status", "in", ["Pending Exits", "Released"]]],
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
    order_by: "modified desc",
    limit_page_length: 50,
  },
  auto: true,
});

const deliveries = computed(() => deliveriesResource.data || []);
const loadErrorMessage = computed(() => resourceErrorMessage(deliveriesResource.error, "errors.loadFailed"));

// The exit flags are ordered 1 -> security, 2 -> logistics, 3 -> receiving.
const EXIT_FLAG = { 1: "exit1_security_cleared", 2: "exit2_logistics_cleared", 3: "exit3_receiving_cleared" };

function exitCleared(del, n) {
  return !!del[EXIT_FLAG[n]];
}

// The next uncleared exit (1..3); 0 once all three are cleared.
function nextExit(del) {
  for (let n = 1; n <= 3; n++) if (!exitCleared(del, n)) return n;
  return 0;
}

// Each gate with the state the track paints it in. Derived here so the template
// stays declarative.
function gates(del) {
  const next = nextExit(del);
  return [1, 2, 3].map((n) => ({
    n,
    label: t("delivery.exit" + n),
    state: exitCleared(del, n) ? "cleared" : n === next ? "current" : "waiting",
  }));
}

function exitLabel(n) {
  return n ? t("delivery.exit" + n) : "";
}

function statusLabel(status) {
  return status === "Released" ? t("delivery.readyToReceive") : t("delivery.awaitingExits");
}

function flash(msg) {
  toast.value = msg;
  setTimeout(() => {
    if (toast.value === msg) toast.value = "";
  }, 3000);
}

function setError(name, err) {
  errorFor.value = name;
  actionError.value = resourceErrorMessage(err);
}

// Clear the next exit checkpoint. The backend enforces role + order and only
// opens the transfer lock (status -> Released) on the third exit.
async function passExit(del) {
  const n = nextExit(del);
  if (!n || busy.value) return;
  busy.value = del.name;
  actionError.value = "";
  errorFor.value = "";
  try {
    await call(EXIT_METHOD[n], { args: { delivery: del.name }, type: "POST" });
    flash(t("delivery.exitCleared"));
    await deliveriesResource.reload();
  } catch (err) {
    setError(del.name, err);
  } finally {
    busy.value = "";
  }
}

function openConfirm(name) {
  selectedDelivery.value = name;
  otpCode.value = "";
  actionError.value = "";
  errorFor.value = "";
}

// Confirm the on-site code; the backend moves the asset and marks it Delivered.
async function confirmReceipt(name) {
  if (otpCode.value.length !== 6 || busy.value) return;
  busy.value = name;
  actionError.value = "";
  errorFor.value = "";
  try {
    await call(API + "confirm_receipt", { args: { delivery: name, code: otpCode.value }, type: "POST" });
    selectedDelivery.value = null;
    otpCode.value = "";
    flash(t("delivery.confirmed"));
    await deliveriesResource.reload();
  } catch (err) {
    setError(name, err);
  } finally {
    busy.value = "";
  }
}
</script>

<style scoped>
.app-main {
  flex: 1;
  padding: 18px 16px 40px;
}

/* ---- header (mirrors Count.vue) -------------------------------------- */
.header-inner {
  position: relative;
  z-index: 1;
  padding: 16px 16px 20px;
}
.header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.header-brand {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}
.header-mark {
  display: grid;
  place-items: center;
  height: 32px;
  width: 32px;
  border-radius: var(--radius);
  color: var(--c-header-bg);
  background: var(--c-header-accent);
  flex-shrink: 0;
}
.header-logo {
  height: 28px;
  width: auto;
  max-width: 140px;
  object-fit: contain;
}
.header-word {
  font-size: var(--fs-h3);
  font-weight: var(--fw-heading);
  letter-spacing: -0.01em;
  color: var(--c-header-ink);
}
.greeting-block {
  margin-top: 14px;
}
.greeting-eyebrow {
  font-size: var(--fs-xs);
  font-weight: var(--fw-semibold);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--c-header-accent);
}
.greeting-title {
  font-size: var(--fs-h1);
  font-weight: var(--fw-heading);
  line-height: 1.15;
  color: var(--c-header-ink);
  margin-top: 2px;
}
.waiting-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin-top: 12px;
  padding: 7px 12px;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--c-header-ink) 14%, transparent);
  color: var(--c-header-ink);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
}

/* ---- generic states (mirrors Count.vue) ------------------------------ */
.state-center {
  text-align: center;
  padding: 32px 16px;
}
.state-icon {
  display: grid;
  place-items: center;
  height: 52px;
  width: 52px;
  margin: 0 auto 14px;
  border-radius: var(--radius-lg);
}
.state-icon-danger {
  color: var(--c-danger);
  background: var(--c-danger-bg);
}
.state-title {
  font-weight: var(--fw-heading);
  font-size: var(--fs-h3);
  color: var(--c-ink);
}
.state-msg {
  margin-top: 6px;
  font-size: var(--fs-sm);
  color: var(--c-muted);
}
.state-btn {
  width: auto;
  padding-inline: 28px;
  margin: 16px auto 0;
}

.empty {
  text-align: center;
  padding: 40px 8px 8px;
}
.empty-burst {
  position: relative;
  display: grid;
  place-items: center;
  height: 104px;
  width: 104px;
  margin: 0 auto 20px;
  color: var(--c-primary);
}
.empty-ring {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: color-mix(in srgb, var(--c-primary) 10%, transparent);
}
.empty-title {
  font-size: var(--fs-h2);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
  line-height: 1.2;
}
.empty-sub {
  margin-top: 8px;
  font-size: var(--fs-sm);
  color: var(--c-muted);
  max-width: 280px;
  margin-inline: auto;
}
.empty-switch {
  width: auto;
  padding-inline: 26px;
  margin: 26px auto 0;
}

/* ---- list ------------------------------------------------------------ */
.list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.list-intro {
  padding: 0 2px;
}
.list-sub {
  margin-top: 4px;
  font-size: var(--fs-sm);
  color: var(--c-muted);
}

/* ---- delivery card --------------------------------------------------- */
.d-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  border-radius: var(--radius);
  border: 1px solid var(--c-border);
  background: var(--c-surface);
  box-shadow: var(--shadow-sm);
}
.d-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.d-id {
  min-width: 0;
}
.d-id-label {
  font-size: var(--fs-2xs);
  font-weight: var(--fw-semibold);
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--c-muted);
}
.d-id-value {
  display: block;
  margin-top: 2px;
  font-size: var(--fs-h3);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
  overflow-wrap: anywhere;
}
.d-id-sub {
  display: block;
  margin-top: 2px;
  font-size: var(--fs-xs);
  color: var(--c-muted);
  overflow-wrap: anywhere;
}
.d-head .pill {
  margin-inline-start: auto;
  flex-shrink: 0;
}

.d-route {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px 14px;
}
.d-kv-key {
  font-size: var(--fs-xs);
  color: var(--c-muted);
}
.d-kv-val {
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  color: var(--c-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ---- the gate track — this screen's one signature element ------------ */
.gate-track {
  display: flex;
  gap: 6px;
  margin: 2px 0 0;
  padding: 0;
  list-style: none;
}
.gate {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.gate-bar {
  height: 6px;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--c-ink) 14%, transparent);
}
.gate-name {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: var(--fs-2xs);
  font-weight: var(--fw-semibold);
  line-height: 1.25;
  color: var(--c-muted);
}
.gate-cleared .gate-bar {
  background: var(--c-success);
}
.gate-cleared .gate-name {
  color: var(--c-success);
}
.gate-current .gate-bar {
  background: var(--c-primary);
}
.gate-current .gate-name {
  color: var(--c-ink);
  font-weight: var(--fw-heading);
}

/* ---- actions --------------------------------------------------------- */
.d-action {
  margin-top: 2px;
}
.otp {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.otp-label {
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  color: var(--c-ink-soft);
}
/* --border-control, not --border: an input has nothing but its edge to say it
   is a control, so it needs the 3:1 UI threshold. */
.otp-input {
  min-height: var(--tap-md);
  width: 100%;
  padding: 10px 14px;
  border-radius: var(--radius);
  border: 1px solid var(--c-border-control);
  background: var(--c-surface-2);
  color: var(--c-ink);
  font-size: var(--fs-h2);
  text-align: center;
  letter-spacing: 0.28em;
  text-indent: 0.28em; /* re-centres text that trailing letter-spacing pushes left */
}
.otp-input::placeholder {
  color: var(--c-muted);
  letter-spacing: 0.28em;
}
.otp-actions {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
}
.otp-actions .btn {
  width: 100%;
}
.d-error {
  margin-top: 2px;
}

/* ---- toast ----------------------------------------------------------- */
.toast {
  position: fixed;
  inset-block-end: calc(84px + env(safe-area-inset-bottom));
  inset-inline: 16px;
  z-index: 60;
  margin-inline: auto;
  width: fit-content;
  max-width: calc(100% - 32px);
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 11px 18px;
  border-radius: var(--radius-pill);
  background: var(--c-success);
  color: var(--c-primary-ink);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  box-shadow: var(--shadow);
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* ---- tablet / iPad (≥768px) ----------------------------------------- */
/* 768px = shared --bp-tablet (frontend_shared/tokens.css); keep in sync —
   CSS @media conditions cannot read a custom property. */
@media (min-width: 768px) {
  .header-inner {
    padding: 24px 28px 28px;
  }
  .app-main {
    padding: 28px 28px 56px;
  }
  .greeting-title {
    font-size: var(--fs-display);
  }
  .list {
    gap: 18px;
  }
  .list-intro .section-title {
    font-size: var(--fs-h1);
  }
  .d-card {
    padding: 18px;
  }
}
</style>
