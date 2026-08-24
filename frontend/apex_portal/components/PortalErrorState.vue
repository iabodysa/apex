<script setup>
import { computed } from "vue";
import { Button } from "frappe-ui";
import { isRetryablePortalError, safeErrorMessage } from "../core/errorMessage.js";
import { __ } from "../core/i18n.js";

const props = defineProps({
  title: { type: String, default: () => __("Could not load the data") },
  message: { type: [String, Object], default: "" },
  fallback: { type: String, default: () => __("Check your connection, then try again.") },
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
    <Button v-if="showRetry" variant="outline" @click="$emit('retry')">{{ __("Retry") }}</Button>
  </section>
</template>
