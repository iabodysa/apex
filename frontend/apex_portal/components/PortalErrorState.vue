<script setup>
import { computed } from "vue";
import { Button } from "frappe-ui";
import { isRetryablePortalError, safeErrorMessage } from "../core/errorMessage.js";

const props = defineProps({
  title: { type: String, default: "تعذّر تحميل البيانات" },
  message: { type: [String, Object], default: "" },
  fallback: { type: String, default: "تحقق من الاتصال ثم حاول مرة أخرى." },
  retryable: { type: Boolean, default: undefined },
});
defineEmits(["retry"]);

const detail = computed(() => safeErrorMessage(props.message, props.fallback, props.title));
const showRetry = computed(() => props.retryable ?? isRetryablePortalError(props.message));
</script>

<template>
  <section class="feature-state feature-state--error" role="alert">
    <h2>{{ title }}</h2>
    <p>{{ detail }}</p>
    <Button v-if="showRetry" variant="outline" @click="$emit('retry')">إعادة المحاولة</Button>
  </section>
</template>
