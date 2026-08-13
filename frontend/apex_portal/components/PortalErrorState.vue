<script setup>
import { computed } from "vue";
import { Button } from "frappe-ui";
import { safeErrorMessage } from "../core/errorMessage.js";

const props = defineProps({
  title: { type: String, default: "تعذّر تحميل البيانات" },
  message: { type: [String, Object], default: "" },
  fallback: { type: String, default: "تحقق من الاتصال ثم حاول مرة أخرى." },
});
defineEmits(["retry"]);

const detail = computed(() => safeErrorMessage(props.message, props.fallback, props.title));
</script>

<template>
  <section class="feature-state feature-state--error" role="alert">
    <h2>{{ title }}</h2>
    <p>{{ detail }}</p>
    <Button variant="outline" @click="$emit('retry')">إعادة المحاولة</Button>
  </section>
</template>
