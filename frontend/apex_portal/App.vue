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
    <RouterView v-slot="{ Component, route }">
      <!-- Keyed on the path only: a filter submit changes the query, and the pages that read
           it watch the query themselves rather than needing a fresh component and a page-0 refetch. -->
      <component :is="Component" :key="route.path" />
    </RouterView>
  </component>
</template>
