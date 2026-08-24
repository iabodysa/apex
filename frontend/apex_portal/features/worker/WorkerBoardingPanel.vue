<script setup>
import { computed } from "vue";
import { Badge, Button } from "frappe-ui";
import { remainingSeconds, workerTransportStatusLabel } from "../../core/displayLabels.js";
import { __ } from "../../core/i18n.js";

const props = defineProps({
  boarding: { type: Object, required: true },
  now: { type: Number, required: true },
  busy: { type: String, default: "" },
});
defineEmits(["wait", "confirm"]);

const canWait = computed(() => props.boarding.dispatch_trip && !["Boarded", "Absent"].includes(props.boarding.status) && Number(props.boarding.wait_count || 0) < Number(props.boarding.wait_max || 0));
const canConfirm = computed(() => props.boarding.boarding_window?.can_confirm && props.boarding.status !== "Boarded");
// "انتظرني" is refused for four different reasons; a grey button that never says which
// one leaves the worker pressing it at the roadside.
const waitReason = computed(() => {
  if (canWait.value) return "";
  if (!props.boarding.dispatch_trip) return __("No trip has been assigned to you yet, so you cannot request a wait.");
  if (props.boarding.status === "Boarded") return __("You are already on the bus, so there is no need to request a wait.");
  if (props.boarding.status === "Absent") return __("Your absence from this trip has been recorded.");
  return __("You have used up the wait requests available for this trip.");
});
// "أنا في الحافلة" also greys once boarding is already recorded, and that branch said nothing —
// the worker read the grey button as the confirmation having failed.
const confirmReason = computed(() => {
  if (canConfirm.value) return "";
  if (props.boarding.status === "Boarded") return __("Your boarding has already been recorded.");
  return __("Boarding confirmation becomes available once the bus reaches your point.");
});
const waitSeconds = computed(() => remainingSeconds(props.boarding.wait_at, props.boarding.wait_window_seconds, props.now));
const notifySeconds = computed(() => remainingSeconds(props.boarding.notify_at, props.boarding.notify_window_seconds, props.now));
</script>

<template>
  <article class="journey-live" aria-live="polite">
    <div class="journey-live__top">
      <div>
        <span class="journey-kicker">{{ __("Current status") }}</span>
        <h3>
          {{ workerTransportStatusLabel(boarding.boarding_window?.state || boarding.status) }}
        </h3>
      </div>
      <Badge :label="workerTransportStatusLabel(boarding.status)" />
    </div>
    <p v-if="boarding.driver_arrived" class="journey-alert">{{ __("The driver has arrived at your pickup point.") }}</p>
    <p v-if="notifySeconds !== null" class="journey-alert journey-alert--notice">
      {{ notifySeconds > 0 ? __("The driver notified you, departure in {0} seconds.", [notifySeconds]) : __("The bus is preparing to depart now.") }}
    </p>
    <p v-if="boarding.wrong_bus" class="journey-alert journey-alert--danger">{{ __("You are at a different bus. Check the trip number before confirming.") }}</p>
    <div class="journey-actions">
      <Button variant="outline" :disabled="!canWait" :loading="busy === 'wait'" @click="$emit('wait')">{{ __("Wait for me") }}</Button>
      <Button theme="green" variant="solid" :disabled="!canConfirm" :loading="busy === 'boarded'" @click="$emit('confirm')">{{ __("I'm on the bus") }}</Button>
    </div>
    <small v-if="boarding.wait_max" class="journey-wait-note">
      {{ __("Wait request {0} of {1}", [boarding.wait_count || 0, boarding.wait_max]) }}
      <template v-if="waitSeconds">{{ __("· Your request is active for {0} seconds", [waitSeconds]) }}</template>
    </small>
    <small v-if="waitReason">{{ waitReason }}</small>
    <small v-if="confirmReason">{{ confirmReason }}</small>
  </article>
</template>
