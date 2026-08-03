<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <Panel :title="t('notifications.title')">
    <template v-if="unread" #status>
      <Badge class="tone-badge" theme="blue" variant="subtle" size="lg" :label="n(unread)" />
    </template>

    <ul v-if="notifications.length" class="note-rows">
      <li v-for="note in notifications" :key="note.name" class="note-row">
        <span class="note-dot" :class="{ 'is-read': note.read }" aria-hidden="true"></span>
        <span class="note-text">
          <span class="note-subject" :class="{ 'is-read': note.read }">{{ note.subject }}</span>
          <span v-if="note.body" class="note-body">{{ note.body }}</span>
        </span>
      </li>
    </ul>

    <EmptyState v-else :title="t('notifications.empty')" :hint="t('notifications.emptyHint')">
      <template #icon><Icon name="bell" :size="22" /></template>
    </EmptyState>
  </Panel>
</template>

<script setup>
import { computed } from "vue";
import { Badge } from "frappe-ui";
import EmptyState from "@shared/components/EmptyState.vue";
import Panel from "./Panel.vue";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";

const { t, n } = useI18n();

const props = defineProps({
  notifications: { type: Array, required: true },
});

const unread = computed(() => props.notifications.filter((note) => !note.read).length);
</script>

<style scoped>
.note-rows {
  display: flex;
  flex-direction: column;
}
.note-row {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-3);
  padding-block: var(--sp-3);
  border-top: var(--border-width) solid var(--c-border);
}
.note-row:first-child {
  border-top: none;
  padding-top: 0;
}
.note-dot {
  flex-shrink: 0;
  height: var(--sp-2);
  width: var(--sp-2);
  margin-top: 6px;
  border-radius: var(--radius-pill);
  background: var(--c-primary);
}
.note-dot.is-read {
  background: var(--c-border-control);
}
.note-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}
.note-subject {
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-ink);
  line-height: 1.4;
}
.note-subject.is-read {
  color: var(--c-ink-soft);
  font-weight: var(--fw-body);
}
.note-body {
  font-size: var(--fs-sm);
  color: var(--c-muted);
  line-height: 1.6;
}
</style>
