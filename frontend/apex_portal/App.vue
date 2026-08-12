<script setup>
import { computed } from "vue";
import MobileShell from "./shells/MobileShell.vue";
import OperationsShell from "./shells/OperationsShell.vue";

const props = defineProps({
  context: { type: Object, required: true },
  title: { type: String, required: true },
  navigation: { type: Array, default: () => [] },
});

const shell = computed(() => (
  props.context.shell === "mobile" ? MobileShell : OperationsShell
));
</script>

<template>
  <component :is="shell" :title="title" :navigation="navigation">
    <RouterView />
  </component>
</template>
