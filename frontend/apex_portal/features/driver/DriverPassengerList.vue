<script setup>
import { computed } from "vue";
import { Badge, Button } from "frappe-ui";
import { remainingSeconds, workerTransportStatusLabel } from "../../core/displayLabels.js";
import { __ } from "../../core/i18n.js";

const props = defineProps({
  workers: { type: Array, default: () => [] },
  busy: { type: String, default: "" },
  waitLimit: { type: Number, default: 0 },
  waitWindowSeconds: { type: Number, default: 0 },
  now: { type: Number, required: true },
  pendingCount: { type: Number, default: 0 },
  graceElapsed: { type: Boolean, default: false },
});
defineEmits(["manual-board", "unmark", "notify", "depart"]);

// Notify and depart are blocked by different things, and one shared line could only ever name one:
// before the grace window closed, a driver with nobody left to notify still read the departure
// sentence and no word about the button he had just pressed.
const notifyReason = computed(() => (props.pendingCount ? "" : __("No one is waiting for you right now, so there is no one to notify.")));
const departReason = computed(() => (props.graceElapsed ? "" : __("Wait for the boarding grace period to end before departing.")));

function waitSeconds(worker) {
  return remainingSeconds(worker.wait_at, props.waitWindowSeconds, props.now);
}
</script>

<template>
  <section class="journey-section">
    <div class="journey-section__title">
      <h3>{{ __("Passengers") }}</h3>
      <span>{{ workers.length }}</span>
    </div>
    <article v-for="worker in workers" :key="worker.employee" class="passenger-row" :class="{ 'has-wait': worker.wait_count }">
      <div>
        <strong dir="auto">{{ worker.employee_name || worker.employee }}</strong>
        <small dir="auto">{{ worker.pickup_point || __("Gathering Point") }}</small>
        <a v-if="worker.phone" class="passenger-call" :href="`tel:${worker.phone}`">{{ __("Call the worker") }}</a>
      </div>
      <span v-if="worker.wait_count" class="wait-signal">
        {{ __("Wait request {0} of {1}", [worker.wait_count, waitLimit]) }}
        <template v-if="waitSeconds(worker) !== null">{{ __("· {0}s", [waitSeconds(worker)]) }}</template>
      </span>
      <Badge :label="workerTransportStatusLabel(worker.status)" />
      <div class="journey-actions">
        <Button v-if="worker.status !== 'Boarded'" variant="outline" :loading="busy === `manual:${worker.employee}`" @click="$emit('manual-board', worker.employee)">{{ __("Manual Check-in") }}</Button>
        <Button v-else variant="outline" :loading="busy === `unmark:${worker.employee}`" @click="$emit('unmark', worker.employee)">{{ __("Not on the bus") }}</Button>
      </div>
    </article>
    <p v-if="!workers.length" class="feature-state">{{ __("No passengers are registered for this trip.") }}</p>
    <div class="journey-actions">
      <Button variant="outline" :disabled="!pendingCount" :loading="busy === 'notify'" @click="$emit('notify')">{{ __("Notify the rest") }}</Button>
      <Button theme="green" variant="solid" :disabled="!graceElapsed" :loading="busy === 'depart'" @click="$emit('depart')">{{ __("Close boarding and depart") }}</Button>
    </div>
    <p v-if="notifyReason" class="journey-hint">{{ __("Notify the rest: {0}", [notifyReason]) }}</p>
    <p v-if="departReason" class="journey-hint">{{ __("Close boarding and depart: {0}", [departReason]) }}</p>
  </section>
</template>
