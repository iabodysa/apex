<script setup>
import { computed, onBeforeUnmount, ref } from "vue";
import { Button, FormControl } from "frappe-ui";
import { createQrScanner } from "./scanner.js";
import { safeErrorMessage } from "../../core/errorMessage.js";
import { __ } from "../../core/i18n.js";

defineProps({
  busy: { type: String, default: "" },
  result: { type: String, default: "" },
});
const emit = defineEmits(["scan", "error"]);

const scanner = createQrScanner();
const token = ref("");
const video = ref(null);
// A driver reads this on a phone, where a tooltip never appears, so the blocked scan says why
// beside it. An empty string means the action is available.
const hint = computed(() => (token.value ? "" : __("Scan the passenger's pass or type its code first.")));

async function startCamera() {
  try {
    await scanner.start(video.value, (code) => emit("scan", code));
  } catch (reason) {
    emit("error", safeErrorMessage(reason, __("Could not start the camera.")));
  }
}

// The camera track stays open until the scanner is stopped, so it is released with this panel.
onBeforeUnmount(scanner.stop);
</script>

<template>
  <section class="journey-section scanner-panel">
    <div class="journey-section__title">
      <h3>{{ __("Boarding pass") }}</h3>
      <span>{{ __("Quick code") }}</span>
    </div>
    <video ref="video" muted playsinline></video>
    <FormControl v-model="token" :label="__('Pass code')" autocomplete="off" />
    <div class="journey-actions">
      <Button variant="outline" @click="startCamera">{{ __("Open camera") }}</Button>
      <Button theme="green" variant="solid" :disabled="!token" :loading="busy === 'scan'" @click="$emit('scan', token)">{{ __("Record boarding") }}</Button>
    </div>
    <p v-if="hint" class="journey-hint">{{ hint }}</p>
    <p v-if="result" role="status">{{ result }}</p>
  </section>
</template>
