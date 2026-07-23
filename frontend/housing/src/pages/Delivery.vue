<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- On-site half of the Facility Asset Delivery 3-exit transfer lock (T-673): the
     mobile surface where a housing supervisor clears their exit checkpoint
     (pass_exit_1/2/3) and, once Released, confirms the on-site code (confirm_receipt).
     Every write goes through the shared @shared/call POST layer; the backend
     fail-closes on role + order, so this UI only surfaces the next pending step. -->
<template>
  <div class="px-4 py-6" :dir="dir">
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-900">{{ t("delivery.title", "Asset Delivery") }}</h1>
      <p class="text-sm text-gray-500 mt-1">{{ t("delivery.subtitle") }}</p>
    </div>

    <!-- Error State -->
    <div v-if="deliveriesResource.error" class="bg-red-50 p-4 rounded-xl mb-6 flex items-start gap-3">
      <Icon name="triangle-alert" class="text-red-500 flex-shrink-0 mt-0.5" />
      <div>
        <p class="text-sm font-medium text-red-800">{{ t("errors.loadFailed", "Failed to load") }}</p>
        <p class="text-xs text-red-600 mt-1">{{ resourceErrorMessage(deliveriesResource.error) }}</p>
        <button class="mt-2 text-xs font-semibold text-red-700 hover:underline" @click="deliveriesResource.reload()">
          {{ t("common.retry", "Retry") }}
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <div v-else-if="deliveriesResource.loading" class="flex flex-col items-center justify-center py-12">
      <div class="w-8 h-8 border-4 border-gray-200 border-t-[var(--c-accent)] rounded-full animate-spin"></div>
      <p class="text-sm text-gray-500 mt-4">{{ t("common.loading", "Loading...") }}</p>
    </div>

    <!-- Empty State -->
    <div v-else-if="!deliveries.length" class="flex flex-col items-center justify-center py-12 text-center">
      <div class="w-16 h-16 bg-gray-50 rounded-full flex items-center justify-center mb-4 text-gray-400">
        <Icon name="check-circle" :size="32" />
      </div>
      <h3 class="text-lg font-semibold text-gray-900">{{ t("delivery.emptyTitle", "All Caught Up") }}</h3>
      <p class="text-sm text-gray-500 mt-1 max-w-[250px]">
        {{ t("delivery.emptySubtitle") }}
      </p>
      <button class="mt-6 text-sm font-semibold text-[var(--c-accent)] hover:underline" @click="deliveriesResource.reload()">
        {{ t("common.refresh", "Refresh List") }}
      </button>
    </div>

    <!-- List of Deliveries -->
    <div v-else class="space-y-4">
      <div
        v-for="del in deliveries"
        :key="del.name"
        class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden"
      >
        <div class="p-4 border-b border-gray-50">
          <div class="flex justify-between items-start mb-2">
            <div>
              <span
                class="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded"
                :class="del.status === 'Released'
                  ? 'text-emerald-700 bg-emerald-50'
                  : 'text-[var(--c-accent)] bg-[color-mix(in_srgb,var(--c-accent)_8%,transparent)]'"
              >
                <Icon :name="del.status === 'Released' ? 'key' : 'truck'" :size="12" />
                {{ statusLabel(del.status) }}
              </span>
              <h3 class="font-bold text-gray-900 mt-2">{{ del.name }}</h3>
              <p v-if="del.asset_serial_number" class="text-xs text-gray-500 mt-0.5">
                {{ t("delivery.asset") }}: {{ del.asset_serial_number }}
              </p>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-y-3 gap-x-4 mt-4 text-sm">
            <div>
              <p class="text-xs text-gray-500">{{ t("delivery.from", "From") }}</p>
              <p class="font-medium text-gray-900 truncate">{{ del.from_building || "—" }}</p>
            </div>
            <div>
              <p class="text-xs text-gray-500">{{ t("delivery.to", "To") }}</p>
              <p class="font-medium text-gray-900 truncate">{{ del.to_building || "—" }}</p>
            </div>
          </div>

          <!-- Exit checkpoint stepper (three exits, in order). -->
          <div class="flex items-center gap-2 mt-4">
            <template v-for="n in 3" :key="n">
              <div
                class="flex-1 h-1.5 rounded-full"
                :class="exitCleared(del, n) ? 'bg-emerald-400' : 'bg-gray-200'"
              ></div>
            </template>
          </div>
          <p class="text-[11px] text-gray-400 mt-1.5">
            {{ del.status === 'Released'
              ? t("delivery.readyToReceive")
              : t("delivery.exitStep", { n: nextExit(del) }) }}
          </p>
        </div>

        <!-- Action Area -->
        <div class="p-4 bg-gray-50/50">
          <!-- Pending Exits: clear the next checkpoint. -->
          <template v-if="del.status === 'Pending Exits'">
            <button
              class="w-full flex items-center justify-center gap-2 py-2.5 bg-[var(--c-accent)] text-white font-semibold rounded-lg disabled:opacity-50 transition-colors"
              :disabled="busy === del.name"
              @click="passExit(del)"
            >
              <Icon v-if="busy === del.name" name="loader" class="animate-spin" :size="16" />
              <Icon v-else name="shield-check" :size="16" />
              {{ t("delivery.clearCheckpoint", { label: exitLabel(nextExit(del)) }) }}
            </button>
          </template>

          <!-- Released: confirm the on-site code. -->
          <template v-else-if="del.status === 'Released'">
            <template v-if="selectedDelivery === del.name">
              <p class="text-xs font-medium text-gray-700 mb-2">{{ t("delivery.enterOtp", "Enter 6-digit confirmation code") }}</p>
              <div class="flex gap-2">
                <input
                  v-model="otpCode"
                  type="text"
                  inputmode="numeric"
                  maxlength="6"
                  pattern="\d*"
                  class="flex-1 bg-white border border-gray-300 rounded-lg px-3 py-2 text-center text-xl tracking-[0.2em] font-mono focus:outline-none focus:ring-2 focus:ring-[var(--c-accent)] focus:border-transparent"
                  placeholder="000000"
                />
                <button
                  class="bg-[var(--c-accent)] text-white font-semibold px-4 rounded-lg flex items-center justify-center disabled:opacity-50"
                  :disabled="otpCode.length !== 6 || busy === del.name"
                  @click="confirmReceipt(del.name)"
                >
                  <Icon v-if="busy === del.name" name="loader" class="animate-spin" />
                  <span v-else>{{ t("common.confirm", "Confirm") }}</span>
                </button>
              </div>
              <div class="mt-2 text-right">
                <button class="text-xs text-gray-500 hover:text-gray-900" @click="selectedDelivery = null">
                  {{ t("common.cancel", "Cancel") }}
                </button>
              </div>
            </template>

            <button
              v-else
              class="w-full flex items-center justify-center gap-2 py-2.5 bg-white border border-gray-200 text-gray-700 font-semibold rounded-lg hover:bg-gray-50 transition-colors"
              @click="openConfirm(del.name)"
            >
              <Icon name="key" :size="16" />
              {{ t("delivery.confirmReceipt", "Confirm Receipt") }}
            </button>
          </template>

          <p v-if="errorFor === del.name && actionError" class="text-xs text-red-600 mt-2">{{ actionError }}</p>
        </div>
      </div>
    </div>

    <!-- Transient success toast. -->
    <transition name="fade">
      <div
        v-if="toast"
        class="fixed left-1/2 -translate-x-1/2 bottom-24 z-50 flex items-center gap-2 bg-gray-900 text-white text-sm font-medium px-4 py-2.5 rounded-full shadow-lg"
      >
        <Icon name="check-circle" :size="16" />
        {{ toast }}
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed } from "vue";
import { createResource } from "frappe-ui";
import { call } from "@shared/call";
import { useI18n, resourceErrorMessage } from "../i18n";
import Icon from "../components/Icon.vue";

const { t, dir } = useI18n();

const API = "apex.habitat.api.facility_asset_delivery.";
const EXIT_METHOD = { 1: API + "pass_exit_1", 2: API + "pass_exit_2", 3: API + "pass_exit_3" };

const selectedDelivery = ref(null);
const otpCode = ref("");
const busy = ref("");        // name of the delivery currently being actioned
const actionError = ref("");
const errorFor = ref("");    // name the current actionError belongs to
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

// The exit flags are ordered 1 -> security, 2 -> logistics, 3 -> receiving.
function exitCleared(del, n) {
  return !!del[{ 1: "exit1_security_cleared", 2: "exit2_logistics_cleared", 3: "exit3_receiving_cleared" }[n]];
}

// The next uncleared exit (1..3); 0 once all three are cleared.
function nextExit(del) {
  for (let n = 1; n <= 3; n++) if (!exitCleared(del, n)) return n;
  return 0;
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
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
