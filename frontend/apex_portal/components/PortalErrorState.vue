<script setup>
import { computed } from "vue";
import { Button } from "frappe-ui";

const props = defineProps({
  title: { type: String, default: "تعذّر تحميل البيانات" },
  message: { type: [String, Object], default: "" },
  fallback: { type: String, default: "تحقق من الاتصال ثم حاول مرة أخرى." },
});
defineEmits(["retry"]);

const detail = computed(() => {
  const source = props.message?.message || props.message || "";
  const clean = String(source)
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 240);
  return !clean || clean === props.title ? props.fallback : clean;
});
</script>

<template>
  <section class="feature-state feature-state--error" role="alert">
    <h2>{{ title }}</h2>
    <p>{{ detail }}</p>
    <Button variant="outline" @click="$emit('retry')">إعادة المحاولة</Button>
  </section>
</template>
