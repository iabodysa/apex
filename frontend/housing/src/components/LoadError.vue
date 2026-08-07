<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="err">
    <Alert theme="red" :title="title" :description="body" :dismissable="false" />
    <Button variant="outline" size="lg" :label="retryLabel" @click="$emit('retry')">
      <template #prefix><Icon name="refresh" :size="16" /></template>
    </Button>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { Alert, Button } from "frappe-ui";
import Icon from "./Icon.vue";

const props = defineProps({
  title: { type: String, required: true },
  detail: { type: String, default: "" },
  hint: { type: String, required: true },
  retryLabel: { type: String, required: true },
});

defineEmits(["retry"]);

const body = computed(() =>
  props.detail && props.detail !== props.title ? props.detail : props.hint,
);
</script>

<style scoped>
.err {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--sp-3);
}
.err :deep(button) {
  min-height: var(--tap-md);
  align-self: center;
  padding-inline: var(--sp-6);
}
</style>
