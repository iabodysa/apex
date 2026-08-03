<!-- Copyright (c) 2026, AFMCO and contributors -->
<template>
  <Panel :title="t('contacts.title')">
    <ul v-if="people.length" class="person-rows">
      <li v-for="person in people" :key="person.role" class="person-row">
        <div class="person-line">
          <Avatar size="2xl" :label="person.name">
            <Icon :name="person.icon" :size="20" />
          </Avatar>
          <span class="person-text">
            <span class="person-role">{{ t(person.role) }}</span>
            <span class="person-name"><bdi>{{ person.name }}</bdi></span>
          </span>
        </div>
        <div v-if="person.phone" class="person-actions">
          <Button class="row-btn" variant="solid" theme="green" :link="'tel:' + person.phone" :label="t('common.call')">
            <template #prefix><Icon name="phone" :size="16" /></template>
          </Button>
          <Button
            v-if="person.whatsapp"
            class="row-btn"
            variant="outline"
            :link="waLink(person.phone)"
            :label="t('common.whatsapp')"
          >
            <template #prefix><Icon name="message" :size="16" /></template>
          </Button>
        </div>
      </li>
    </ul>

    <EmptyState v-else :title="t('contacts.empty')" :hint="t('contacts.emptyHint')">
      <template #icon><Icon name="phone" :size="22" /></template>
    </EmptyState>
  </Panel>
</template>

<script setup>
import { computed } from "vue";
import { Avatar, Button } from "frappe-ui";
import EmptyState from "@shared/components/EmptyState.vue";
import Panel from "@shared/components/Panel.vue";
import Icon from "./Icon.vue";
import { useI18n } from "../i18n";
import { waLink } from "../utils/phone";

const { t } = useI18n();

const props = defineProps({
  contacts: { type: Object, default: null },
});

const people = computed(() => {
  const data = props.contacts || {};
  const rows = [];
  const inCharge = data.building_in_charge;
  if (inCharge) {
    rows.push({
      role: "contacts.buildingInCharge",
      icon: "user",
      name: inCharge.name,
      phone: inCharge.phone,
      whatsapp: !!inCharge.phone,
    });
  }
  const driver = data.today_driver;
  if (driver) {
    rows.push({
      role: "contacts.todayDriver",
      icon: "truck",
      name: driver.full_name,
      phone: driver.phone,
      whatsapp: !!driver.phone,
    });
  }
  const office = data.housing_office_number;
  if (office) {
    rows.push({
      role: "contacts.housingOffice",
      icon: "building",
      name: office,
      phone: office,
      whatsapp: false,
    });
  }
  return rows;
});
</script>

<style scoped>
.person-rows {
  display: flex;
  flex-direction: column;
}
.person-row {
  padding-block: var(--sp-3);
  border-top: var(--border-width) solid var(--c-border);
}
.person-row:first-child {
  border-top: none;
  padding-top: 0;
}
.person-line {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}
.person-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.person-role {
  font-size: var(--fs-sm);
  color: var(--c-muted);
}
.person-name {
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-ink);
  line-height: 1.4;
  overflow-wrap: anywhere;
}
.person-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
  margin-top: var(--sp-3);
}
.person-actions :deep(.row-btn) {
  flex: 1;
}
</style>
