<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <Alert
    class="wait-alert"
    theme="yellow"
    :title="t('trips.waitRequestTitle')"
    :dismissable="true"
    @dismiss="$emit('dismiss')"
  >
    <template #icon><Icon name="alert" :size="20" /></template>
    <template #description>
      <p class="wait-body">
        <bdi>{{ request.employee }}</bdi> {{ t("trips.waitRequestBody") }}
      </p>
      <p v-if="request.trip" class="wait-body">
        {{ t("trips.waitRequestTrip", { trip: request.trip }) }}
      </p>
    </template>
    <template #footer>
      <Badge
        class="tone-badge wait-count"
        theme="orange"
        variant="outline"
        size="lg"
        :label="t('trips.waitSeconds', { n: n(seconds) })"
      />
    </template>
  </Alert>
</template>

<script setup>
import { onUnmounted, ref, watch } from "vue";
import { Alert, Badge } from "frappe-ui";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const { t, n } = useI18n();

const props = defineProps({
  request: { type: Object, required: true },
});

const emit = defineEmits(["dismiss"]);

const seconds = ref(0);
let timer = null;

function chime() {
  try {
    const audio = new (window.AudioContext || window.webkitAudioContext)();
    const tone = audio.createOscillator();
    const gain = audio.createGain();
    tone.connect(gain);
    gain.connect(audio.destination);
    tone.type = "sine";
    tone.frequency.setValueAtTime(880, audio.currentTime);
    gain.gain.setValueAtTime(0.5, audio.currentTime);
    tone.start();
    tone.stop(audio.currentTime + 0.3);
  } catch (e) {
    return;
  }
}

function stop() {
  if (timer) clearInterval(timer);
  timer = null;
}

watch(
  () => props.request,
  (value) => {
    stop();
    if (!value) return;
    seconds.value = value.seconds;
    chime();
    timer = setInterval(() => {
      seconds.value -= 1;
      if (seconds.value <= 0) {
        stop();
        emit("dismiss");
      }
    }, 1000);
  },
  { immediate: true },
);

onUnmounted(stop);
</script>

<style scoped>
.wait-body {
  font-size: var(--fs-sm);
  line-height: 1.5;
  color: var(--c-ink-soft);
}
.wait-count {
  font-variant-numeric: tabular-nums;
}
</style>
