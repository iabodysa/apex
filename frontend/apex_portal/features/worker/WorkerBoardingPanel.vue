<script setup>
import { computed } from "vue";
import { Badge, Button } from "frappe-ui";
import { remainingSeconds, workerTransportStatusLabel } from "../../core/displayLabels.js";

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
  if (!props.boarding.dispatch_trip) return "لم تُسند لك رحلة بعد، فلا يمكن طلب الانتظار.";
  if (props.boarding.status === "Boarded") return "أنت على متن الحافلة، ولا حاجة لطلب الانتظار.";
  if (props.boarding.status === "Absent") return "سُجّل غيابك عن هذه الرحلة.";
  return "استهلكت طلبات الانتظار المتاحة لهذه الرحلة.";
});
// "أنا في الحافلة" also greys once boarding is already recorded, and that branch said nothing —
// the worker read the grey button as the confirmation having failed.
const confirmReason = computed(() => {
  if (canConfirm.value) return "";
  if (props.boarding.status === "Boarded") return "سجّلنا صعودك بالفعل.";
  return "يتاح تأكيد الصعود عندما تصل الحافلة إلى نقطتك.";
});
const waitSeconds = computed(() => remainingSeconds(props.boarding.wait_at, props.boarding.wait_window_seconds, props.now));
const notifySeconds = computed(() => remainingSeconds(props.boarding.notify_at, props.boarding.notify_window_seconds, props.now));
</script>

<template>
  <article class="journey-live" aria-live="polite">
    <div class="journey-live__top">
      <div>
        <span class="journey-kicker">الحالة الآن</span>
        <h3>
          {{ workerTransportStatusLabel(boarding.boarding_window?.state || boarding.status) }}
        </h3>
      </div>
      <Badge :label="workerTransportStatusLabel(boarding.status)" />
    </div>
    <p v-if="boarding.driver_arrived" class="journey-alert">وصل السائق إلى نقطة تجمعك.</p>
    <p v-if="notifySeconds !== null" class="journey-alert journey-alert--notice">
      {{ notifySeconds > 0 ? `السائق نبهك، موعد المغادرة خلال ${notifySeconds} ثانية.` : "الحافلة تستعد للمغادرة الآن." }}
    </p>
    <p v-if="boarding.wrong_bus" class="journey-alert journey-alert--danger">أنت عند حافلة مختلفة. راجع رقم الرحلة قبل التأكيد.</p>
    <div class="journey-actions">
      <Button variant="outline" :disabled="!canWait" :loading="busy === 'wait'" @click="$emit('wait')">انتظرني</Button>
      <Button theme="green" variant="solid" :disabled="!canConfirm" :loading="busy === 'boarded'" @click="$emit('confirm')">أنا في الحافلة</Button>
    </div>
    <small v-if="boarding.wait_max" class="journey-wait-note">
      طلب الانتظار {{ boarding.wait_count || 0 }} من {{ boarding.wait_max }}
      <template v-if="waitSeconds">· طلبك فعال لمدة {{ waitSeconds }} ثانية</template>
    </small>
    <small v-if="waitReason">{{ waitReason }}</small>
    <small v-if="confirmReason">{{ confirmReason }}</small>
  </article>
</template>
