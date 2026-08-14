<script setup>
import { computed } from "vue";
import { Badge, Button } from "frappe-ui";
import { remainingSeconds, workerTransportStatusLabel } from "../../core/displayLabels.js";

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

// Departure is the harder block, so it is named first when both actions are unavailable.
const hint = computed(() => {
  if (!props.graceElapsed) return "انتظر انتهاء مهلة الصعود قبل المغادرة.";
  return props.pendingCount ? "" : "لا أحد بانتظارك الآن.";
});

function waitSeconds(worker) {
  return remainingSeconds(worker.wait_at, props.waitWindowSeconds, props.now);
}
</script>

<template>
  <section class="journey-section">
    <div class="journey-section__title">
      <h3>الركاب</h3>
      <span>{{ workers.length }}</span>
    </div>
    <article v-for="worker in workers" :key="worker.employee" class="passenger-row" :class="{ 'has-wait': worker.wait_count }">
      <div>
        <strong>{{ worker.employee_name || worker.employee }}</strong>
        <small>{{ worker.pickup_point || "نقطة التجمع" }}</small>
        <a v-if="worker.phone" class="passenger-call" :href="`tel:${worker.phone}`">اتصل بالعامل</a>
      </div>
      <span v-if="worker.wait_count" class="wait-signal">
        طلب الانتظار {{ worker.wait_count }} من {{ waitLimit }}
        <template v-if="waitSeconds(worker) !== null">· {{ waitSeconds(worker) }} ث</template>
      </span>
      <Badge :label="workerTransportStatusLabel(worker.status)" />
      <div class="journey-actions">
        <Button v-if="worker.status !== 'Boarded'" variant="outline" :loading="busy === `manual:${worker.employee}`" @click="$emit('manual-board', worker.employee)">تسجيل يدوي</Button>
        <Button v-else variant="outline" :loading="busy === `unmark:${worker.employee}`" @click="$emit('unmark', worker.employee)">ليس في الحافلة</Button>
      </div>
    </article>
    <p v-if="!workers.length" class="feature-state">لا يوجد ركاب مسجلون لهذه الرحلة.</p>
    <div class="journey-actions">
      <Button variant="outline" :disabled="!pendingCount" :loading="busy === 'notify'" @click="$emit('notify')">نبه المتبقين</Button>
      <Button theme="green" variant="solid" :disabled="!graceElapsed" :loading="busy === 'depart'" @click="$emit('depart')">أغلق الصعود وغادر</Button>
    </div>
    <p v-if="hint" class="journey-hint">{{ hint }}</p>
  </section>
</template>
