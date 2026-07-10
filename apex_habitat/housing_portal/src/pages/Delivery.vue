<template>
  <div class="px-4 py-6" :dir="dir">
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-900">{{ t("delivery.title", "Asset Delivery") }}</h1>
      <p class="text-sm text-gray-500 mt-1">{{ t("delivery.subtitle", "Confirm receipt of assets transferred to your location") }}</p>
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
        {{ t("delivery.emptySubtitle", "There are no pending asset deliveries awaiting your confirmation.") }}
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
              <span class="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-[var(--c-accent)] bg-[color-mix(in_srgb,var(--c-accent)_8%,transparent)] px-2 py-0.5 rounded">
                <Icon name="truck" :size="12" />
                {{ del.status }}
              </span>
              <h3 class="font-bold text-gray-900 mt-2">{{ del.name }}</h3>
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
        </div>

        <!-- Action Area -->
        <div class="p-4 bg-gray-50/50">
          <template v-if="selectedDelivery === del.name">
            <p class="text-xs font-medium text-gray-700 mb-2">{{ t("delivery.enterOtp", "Enter 6-digit confirmation code") }}</p>
            <div class="flex gap-2">
              <input 
                v-model="otpCode"
                type="text" 
                maxlength="6"
                pattern="\d*"
                class="flex-1 bg-white border border-gray-300 rounded-lg px-3 py-2 text-center text-xl tracking-[0.2em] font-mono focus:outline-none focus:ring-2 focus:ring-[var(--c-accent)] focus:border-transparent"
                placeholder="000000"
              />
              <button 
                class="bg-[var(--c-accent)] text-white font-semibold px-4 rounded-lg flex items-center justify-center disabled:opacity-50"
                :disabled="otpCode.length !== 6 || confirming"
                @click="confirmReceipt(del.name)"
              >
                <Icon v-if="confirming" name="loader" class="animate-spin" />
                <span v-else>{{ t("common.confirm", "Confirm") }}</span>
              </button>
            </div>
            <div class="mt-2 text-right">
              <button class="text-xs text-gray-500 hover:text-gray-900" @click="selectedDelivery = null">
                {{ t("common.cancel", "Cancel") }}
              </button>
            </div>
            <p v-if="confirmError" class="text-xs text-red-600 mt-2">{{ confirmError }}</p>
          </template>
          
          <button 
            v-else
            class="w-full flex items-center justify-center gap-2 py-2.5 bg-white border border-gray-200 text-gray-700 font-semibold rounded-lg hover:bg-gray-50 transition-colors"
            @click="openConfirm(del.name)"
          >
            <Icon name="key" :size="16" />
            {{ t("delivery.confirmReceipt", "Confirm Receipt") }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from "vue";
import { createResource } from "frappe-ui";
import { useI18n, resourceErrorMessage } from "../i18n";
import Icon from "../components/Icon.vue";

const { t, dir } = useI18n();

const selectedDelivery = ref(null);
const otpCode = ref("");
const confirming = ref(false);
const confirmError = ref("");

// Fetch released deliveries
const deliveriesResource = createResource({
  url: "frappe.client.get_list",
  params: {
    doctype: "Facility Asset Delivery",
    filters: [["status", "in", ["Released"]]],
    fields: ["name", "status", "from_building", "to_building"],
    limit_page_length: 50,
  },
  auto: true,
});

const deliveries = computed(() => deliveriesResource.data || []);

function openConfirm(name) {
  selectedDelivery.value = name;
  otpCode.value = "";
  confirmError.value = "";
}

async function confirmReceipt(name) {
  if (otpCode.value.length !== 6) return;
  
  confirming.value = true;
  confirmError.value = "";
  
  try {
    const res = createResource({
      url: "apex_habitat.habitat.api.facility_asset_delivery.confirm_receipt",
      params: {
        delivery: name,
        code: otpCode.value,
      },
    });
    
    await res.fetch();
    
    // Success! Remove from list or refresh
    selectedDelivery.value = null;
    otpCode.value = "";
    await deliveriesResource.reload();
    
    // Optional: Show success toast/alert
    alert(t("success.saved", { n: 1 }) || "Confirmed successfully!");
    
  } catch (err) {
    confirmError.value = resourceErrorMessage(err);
  } finally {
    confirming.value = false;
  }
}
</script>
