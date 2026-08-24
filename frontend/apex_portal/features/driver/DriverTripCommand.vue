<script setup>
import { computed } from "vue";
import { Button } from "frappe-ui";
import { __ } from "../../core/i18n.js";

const props = defineProps({
  boardedCount: { type: Number, default: 0 },
  pendingCount: { type: Number, default: 0 },
  completedStops: { type: Number, default: 0 },
  started: { type: Boolean, default: false },
  busy: { type: String, default: "" },
});
defineEmits(["start", "finish"]);

// A driver reads this on a phone, where a tooltip never appears, so every blocked action says why
// beside it. An empty string means the action is available.
const hint = computed(() => (props.started ? __("The trip has already started.") : __("Start the trip first.")));
</script>

<template>
  <section class="journey-command">
    <div class="journey-command__metric">
      <strong>{{ boardedCount }}</strong>
      <span>{{ __("boarded") }}</span>
    </div>
    <div class="journey-command__metric">
      <strong>{{ pendingCount }}</strong>
      <span>{{ __("Waiting for you") }}</span>
    </div>
    <div class="journey-command__metric">
      <strong>{{ completedStops }}</strong>
      <span>{{ __("Stops completed") }}</span>
    </div>
    <div class="journey-actions journey-command__actions">
      <Button theme="green" variant="solid" :disabled="started" :loading="busy === 'start'" @click="$emit('start')">{{ __("Start trip") }}</Button>
      <Button variant="outline" :disabled="!started" :loading="busy === 'finish'" @click="$emit('finish')">{{ __("End trip") }}</Button>
    </div>
    <p v-if="hint" class="journey-hint">{{ hint }}</p>
  </section>
</template>
