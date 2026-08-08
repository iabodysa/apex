<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div ref="stage" class="scanner-overlay" role="dialog" aria-modal="true" :aria-label="t('boarding.title')">
    <div class="scanner-bar">
      <span class="font-bold">{{ t("boarding.title") }}</span>
      <button class="scanner-close" :aria-label="t('boarding.close')" @click="close">
        <Icon name="x" :size="20" />
      </button>
    </div>

    <div class="scanner-stage">
      <video ref="video" class="scanner-video" playsinline muted></video>
      <div v-if="phase === 'scanning'" class="scanner-reticle" aria-hidden="true"></div>

      <div v-if="phase === 'starting'" class="scanner-note">
        <div class="spinner"></div>
        <p>{{ t("boarding.starting") }}</p>
      </div>
      <div v-else-if="phase === 'error'" class="scanner-note">
        <p>{{ errorMsg }}</p>
      </div>

      <div v-else-if="phase === 'result'" class="scanner-result" :class="resultClass">
        <div class="result-icon"><Icon :name="resultIcon" :size="40" /></div>
        <p class="result-title">{{ t(resultTitleKey) }}</p>
        <p class="result-hint">{{ t(resultHintKey) }}</p>
      </div>
    </div>

    <p v-if="phase === 'scanning'" class="scanner-hint">{{ t("boarding.hint") }}</p>

    <div class="scanner-actions">
      <button v-if="phase === 'result'" class="btn btn-primary" @click="rescan">
        {{ t("boarding.again") }}
      </button>
      <button class="btn btn-outline" @click="close">{{ t("boarding.close") }}</button>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { createResource } from "frappe-ui";
import { useOverlay } from "@shared/useOverlay.js";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const { t } = useI18n();

const emit = defineEmits(["close", "boarded"]);
const props = defineProps({
  stopName: { type: String, default: null },
  accommodationBuilding: { type: String, default: null },
});

const stage = ref(null);
const video = ref(null);
const phase = ref("starting");
const errorMsg = ref("");
const lastResult = ref(null);

let stream = null;
let detector = null;
let rafId = null;
let stopped = false;
let busy = false;

const scan = createResource({
  url: "apex.salis.api.boarding.scan_boarding_pass",
});

const RESULTS = {
  Valid: { class: "is-valid", icon: "badge", title: "boarding.resultValid", hint: "boarding.validHint" },
  Duplicate: { class: "is-warn", icon: "alert", title: "boarding.resultDuplicate", hint: "boarding.duplicateHint" },
  "Wrong Trip": { class: "is-err", icon: "alert", title: "boarding.resultWrongTrip", hint: "boarding.wrongTripHint" },
  Expired: { class: "is-err", icon: "alert", title: "boarding.resultExpired", hint: "boarding.expiredHint" },
  "Invalid Token": { class: "is-err", icon: "alert", title: "boarding.resultInvalid", hint: "boarding.invalidHint" },
};
const meta = computed(() => RESULTS[lastResult.value] || RESULTS["Invalid Token"]);
const resultClass = computed(() => meta.value.class);
const resultIcon = computed(() => meta.value.icon);
const resultTitleKey = computed(() => meta.value.title);
const resultHintKey = computed(() => meta.value.hint);

function supported() {
  return (
    typeof window !== "undefined" &&
    "BarcodeDetector" in window &&
    navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === "function"
  );
}

async function start() {
  if (!supported()) {
    phase.value = "error";
    errorMsg.value = t("boarding.unsupported");
    return;
  }
  try {
    detector = new window.BarcodeDetector({ formats: ["qr_code"] });
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
      audio: false,
    });
    if (stopped) return releaseStream();
    video.value.srcObject = stream;
    await video.value.play();
    phase.value = "scanning";
    loop();
  } catch (e) {
    phase.value = "error";
    errorMsg.value = t("boarding.cameraDenied");
  }
}

async function loop() {
  if (stopped || phase.value !== "scanning" || !video.value) return;
  try {
    const codes = await detector.detect(video.value);
    const token = codes && codes.length ? codes[0].rawValue : null;
    if (token && !busy) {
      await submit(token);
      return;
    }
  } catch (e) {
  }
  rafId = requestAnimationFrame(loop);
}

async function submit(token) {
  busy = true;
  pauseCamera();
  try {
    const params = { pass_token: token };
    if (props.stopName) params.stop_name = props.stopName;
    if (props.accommodationBuilding) params.accommodation_building = props.accommodationBuilding;
    const res = await scan.submit(params);
    lastResult.value = res?.result || "Invalid Token";
    phase.value = "result";
    if (lastResult.value === "Valid") emit("boarded", res);
  } catch (e) {
    lastResult.value = "Invalid Token";
    phase.value = "result";
  } finally {
    busy = false;
  }
}

async function rescan() {
  lastResult.value = null;
  if (!stream) return start();
  try {
    await video.value.play();
  } catch (e) {
  }
  phase.value = "scanning";
  loop();
}

function pauseCamera() {
  if (rafId) cancelAnimationFrame(rafId);
  rafId = null;
  try {
    video.value && video.value.pause();
  } catch (e) {
  }
}

function releaseStream() {
  if (stream) {
    stream.getTracks().forEach((tk) => tk.stop());
    stream = null;
  }
}

function close() {
  emit("close");
}

useOverlay({ active: () => true, container: stage, close });

onMounted(start);
onBeforeUnmount(() => {
  stopped = true;
  if (rafId) cancelAnimationFrame(rafId);
  releaseStream();
});
</script>

<style scoped>
.scanner-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  flex-direction: column;
  background: #000;
  color: #fff;
}
.scanner-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px calc(14px + env(safe-area-inset-top));
  padding-top: calc(14px + env(safe-area-inset-top));
}
.scanner-close {
  font-size: 20px;
  line-height: 1;
  padding: 6px 10px;
  border-radius: var(--radius-pill);
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
}
.scanner-stage {
  position: relative;
  flex: 1;
  overflow: hidden;
  display: grid;
  place-items: center;
}
.scanner-video {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.scanner-reticle {
  position: absolute;
  width: 64%;
  max-width: 280px;
  aspect-ratio: 1;
  border: 3px solid rgba(255, 255, 255, 0.9);
  border-radius: 18px;
  box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.35);
}
.scanner-note {
  position: absolute;
  text-align: center;
  padding: 24px;
  max-width: 320px;
}
.scanner-note .spinner {
  margin: 0 auto 12px;
}
.scanner-result {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 24px;
}
.scanner-result.is-valid { background: var(--c-success); }
.scanner-result.is-warn { background: var(--c-warning); }
.scanner-result.is-err { background: var(--c-danger); }
.result-icon {
  width: 72px;
  height: 72px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.2);
  margin-bottom: 14px;
}
.result-title {
  font-size: 1.375rem;
  font-weight: 800;
}
.result-hint {
  margin-top: 6px;
  opacity: 0.9;
}
.scanner-hint {
  text-align: center;
  font-size: 0.875rem;
  padding: 10px 16px 0;
  opacity: 0.85;
}
.scanner-actions {
  display: flex;
  gap: 10px;
  padding: 16px;
  padding-bottom: calc(16px + env(safe-area-inset-bottom));
}
.scanner-actions .btn {
  flex: 1;
}
</style>
