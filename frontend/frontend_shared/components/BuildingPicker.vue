<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="picker">
    <div class="picker-hero">
      <div class="picker-mark"><Icon name="building" :size="26" /></div>
      <h2 class="picker-title">{{ t("building.title") }}</h2>
      <p class="picker-sub">{{ t("building.subtitle") }}</p>
    </div>

    <div v-if="loading" class="picker-loading">
      <div class="spinner mx-auto"></div>
    </div>

    <div v-else-if="error" class="status-note status-err">{{ error }}</div>

    <div v-else-if="!buildings.length" class="picker-empty">
      <Icon name="building" :size="22" />
      <p>{{ t("building.empty") }}</p>
    </div>

    <template v-else>
      <label v-if="buildings.length > 6" class="search-wrap">
        <Icon name="search" :size="16" />
        <input v-model="q" class="search-input" :placeholder="t('building.search')" />
      </label>

      <ul class="b-list">
        <li v-for="b in filtered" :key="b.name">
          <button type="button" class="b-item" @click="$emit('select', b.name, b.building_name || b.name)">
            <span class="b-icon"><Icon name="building" :size="18" /></span>
            <span class="b-name">{{ b.building_name || b.name }}</span>
            <Icon class="b-go" name="chevron" :size="18" />
          </button>
        </li>
      </ul>
    </template>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { createListResource } from "frappe-ui";
import Icon from "@/components/Icon.vue";
import { useI18n, resourceErrorMessage } from "@/i18n";

const emit = defineEmits(["select"]);
const { t } = useI18n();

const error = ref("");
const q = ref("");

const buildingsRes = createListResource({
  doctype: "Building",
  fields: ["name", "building_name"],
  orderBy: "building_name asc",
  pageLength: 99999,
  auto: true,
  onSuccess: (rows) => {
    if (Array.isArray(rows) && rows.length === 1) {
      const only = rows[0];
      emit("select", only.name, only.building_name || only.name);
    }
  },
  onError: (e) => {
    error.value = resourceErrorMessage(e, "errors.loadError");
  },
});

const buildings = computed(() => buildingsRes.data || []);
const loading = computed(() => buildingsRes.list.loading);

const filtered = computed(() => {
  const term = q.value.trim().toLowerCase();
  if (!term) return buildings.value;
  return buildings.value.filter((b) =>
    (b.building_name || b.name || "").toLowerCase().includes(term),
  );
});
</script>

<style scoped>
.picker {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.picker-hero {
  text-align: center;
  padding-top: var(--sp-2);
}
.picker-mark {
  display: grid;
  place-items: center;
  height: 56px;
  width: 56px;
  margin: 0 auto var(--sp-3);
  border-radius: var(--radius-lg);
  color: var(--c-primary);
  background: color-mix(in srgb, var(--c-primary) 12%, transparent);
}
.picker-title {
  font-size: var(--fs-h2);
  font-weight: var(--fw-heading);
  color: var(--c-ink);
}
.picker-sub {
  margin-top: var(--sp-1);
  font-size: var(--fs-sm);
  color: var(--c-muted);
}
.picker-loading,
.picker-empty {
  text-align: center;
  padding: var(--sp-6) 0;
  color: var(--c-muted);
}
.picker-empty p {
  margin-top: var(--sp-2);
  font-size: var(--fs-sm);
}

.search-wrap {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: 0 var(--sp-3);
  border: 1px solid var(--c-border-strong);
  border-radius: var(--radius);
  background: var(--c-surface);
  color: var(--c-muted);
}
.search-input {
  flex: 1;
  border: none;
  background: transparent;
  padding: var(--sp-3) 0;
  font-family: var(--font);
  font-size: var(--fs-body);
  color: var(--c-ink);
}
.search-input:focus {
  outline: none;
}
.search-input:focus-visible {
  outline: 3px solid var(--c-focus);
  outline-offset: 2px;
}

.b-list {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.b-item {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  width: 100%;
  padding: 14px;
  border-radius: var(--radius);
  border: 1px solid var(--c-border);
  background: var(--c-surface);
  cursor: pointer;
  text-align: start;
  transition:
    transform 0.08s ease,
    border-color 0.15s ease,
    background 0.15s ease;
}
.b-item:active {
  transform: scale(0.985);
}
.b-item:hover {
  border-color: var(--c-border-strong);
  background: var(--c-surface-2, var(--c-surface));
}
.b-icon {
  display: grid;
  place-items: center;
  height: 36px;
  width: 36px;
  border-radius: var(--radius);
  flex-shrink: 0;
  color: var(--c-primary);
  background: color-mix(in srgb, var(--c-primary) 10%, transparent);
}
.b-name {
  flex: 1;
  min-width: 0;
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-ink);
}
.b-go {
  color: var(--c-muted);
  flex-shrink: 0;
}

@media (min-width: 768px) {
  .b-list {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: var(--sp-3);
  }
  .b-item {
    padding: var(--sp-4);
  }
  .picker-title {
    font-size: var(--fs-h1);
  }
}
</style>
