<script setup>
import { computed, onBeforeUnmount, ref } from "vue";
import { Button, FormControl } from "frappe-ui";
import { createQrScanner } from "./scanner.js";
import { safeErrorMessage } from "../../core/errorMessage.js";

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
const hint = computed(() => (token.value ? "" : "امسح بطاقة الراكب أو اكتب رمزها أولاً."));

async function startCamera() {
  try {
    await scanner.start(video.value, (code) => emit("scan", code));
  } catch (reason) {
    emit("error", safeErrorMessage(reason, "تعذّر تشغيل الكاميرا."));
  }
}

// The camera track stays open until the scanner is stopped, so it is released with this panel.
onBeforeUnmount(scanner.stop);
</script>

<template>
  <section class="journey-section scanner-panel">
    <div class="journey-section__title">
      <h3>بطاقة الصعود</h3>
      <span>رمز سريع</span>
    </div>
    <video ref="video" muted playsinline></video>
    <FormControl v-model="token" label="رمز البطاقة" autocomplete="off" />
    <div class="journey-actions">
      <Button variant="outline" @click="startCamera">افتح الكاميرا</Button>
      <Button theme="green" variant="solid" :disabled="!token" :loading="busy === 'scan'" @click="$emit('scan', token)">سجل الصعود</Button>
    </div>
    <p v-if="hint" class="journey-hint">{{ hint }}</p>
    <p v-if="result" role="status">{{ result }}</p>
  </section>
</template>
