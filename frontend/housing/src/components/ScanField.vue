<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="scan">
    <div class="scan-row">
      <FormControl
        class="scan-input"
        type="text"
        size="lg"
        autocomplete="off"
        :label="t('custody.typeCode')"
        v-model="typed"
        @keyup.enter="submitTyped"
      />
      <Button
        class="scan-go"
        size="xl"
        variant="subtle"
        :label="t('common.search')"
        :disabled="!typed.trim()"
        @click="submitTyped"
      >
        <template #icon><Icon name="search" :size="20" /></template>
      </Button>
    </div>

    <Button
      v-if="supported"
      size="xl"
      variant="outline"
      :label="live ? t('custody.scanStop') : t('custody.scanStart')"
      @click="live ? stop() : start()"
    >
      <template #prefix><Icon name="qr" :size="18" /></template>
    </Button>

    <p v-if="!supported" class="hint">{{ stateHint }}</p>
    <p v-else-if="live" class="hint">{{ t("custody.scanHint") }}</p>
    <p v-if="cameraError" class="status-note status-err">{{ cameraError }}</p>

    <video v-show="live" ref="videoEl" class="scan-video" playsinline muted></video>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref } from "vue";
import { Button, FormControl } from "frappe-ui";
import { cameraFailure, cameraState, onCameraChange } from "@shared/camera";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const emit = defineEmits(["code"]);
const { t } = useI18n();

const typed = ref("");
const live = ref(false);
const cameraError = ref("");
const videoEl = ref(null);

const state = ref("unsupported");
const supported = computed(() => state.value === "ready");
const stateHint = computed(() =>
  state.value === "ready" ? "" : t(`custody.camera_${state.value}`),
);

async function readCamera() {
  state.value = await cameraState();
}
readCamera();
const stopWatchingDevices = onCameraChange(readCamera);

let stream = null;
let detector = null;
let timer = 0;

function submitTyped() {
  const code = typed.value.trim();
  if (!code) return;
  typed.value = "";
  emit("code", code);
}

async function start() {
  cameraError.value = "";
  try {
    detector = detector || new window.BarcodeDetector();
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
    });
    live.value = true;
    const video = videoEl.value;
    video.srcObject = stream;
    await video.play();
    timer = window.setInterval(scanFrame, 400);
  } catch (e) {
    cameraError.value = t(`custody.camera_${cameraFailure(e)}`);
    stop();
    readCamera();
  }
}

async function scanFrame() {
  if (!live.value || !videoEl.value) return;
  try {
    const found = await detector.detect(videoEl.value);
    if (found && found.length && found[0].rawValue) {
      const code = String(found[0].rawValue).trim();
      stop();
      if (code) emit("code", code);
    }
  } catch (e) {
    return;
  }
}

function stop() {
  live.value = false;
  if (timer) {
    window.clearInterval(timer);
    timer = 0;
  }
  if (stream) {
    stream.getTracks().forEach((track) => track.stop());
    stream = null;
  }
  if (videoEl.value) videoEl.value.srcObject = null;
}

onUnmounted(() => {
  stop();
  stopWatchingDevices();
});
</script>

<style scoped>
.scan {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.scan-row {
  display: flex;
  align-items: flex-end;
  gap: var(--sp-2);
}
.scan-input {
  flex: 1;
  min-width: 0;
}
.scan-go :deep(button),
.scan-go {
  min-height: var(--tap-min);
  min-width: var(--tap-min);
}
.scan-video {
  width: 100%;
  max-height: 240px;
  border-radius: var(--radius);
  background: var(--c-ink);
  object-fit: cover;
}
</style>
