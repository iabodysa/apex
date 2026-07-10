<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- Building resolver/selector. Loads the buildings the signed-in user may read
     (standard frappe.client.get_list, role- and permission-scoped on the server)
     and lets them pick one. If the account is scoped to a single building it is
     auto-selected and confirmed, so the common case is one tap to start. -->
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
import Icon from "./Icon.vue";
import { useI18n, resourceErrorMessage } from "../i18n";

const emit = defineEmits(["select"]);
const { t } = useI18n();

const error = ref("");
const q = ref("");

// frappe-ui list resource over the same role-/permission-scoped get_list the
// shared call() helper used — returns the identical { name, building_name } rows,
// with CSRF handled by frappeRequest (configured in main.js).
const buildingsRes = createListResource({
  doctype: "Building",
  fields: ["name", "building_name"],
  orderBy: "building_name asc",
  // createListResource has NO "all rows" sentinel: pageLength 0/undefined falls
  // back to its default of 20. The old fetch used limit_page_length:0 (all), so we
  // set a ceiling well above any realistic building count to preserve "show all".
  pageLength: 99999,
  auto: true,
  onSuccess: (rows) => {
    // Scoped to exactly one building -> auto-select; one tap becomes zero.
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
// createListResource exposes loading on its inner `.list` resource, not on the
// top-level object — read it there so the spinner state is preserved.
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
  gap: 16px;
}
.picker-hero {
  text-align: center;
  padding-top: 8px;
}
.picker-mark {
  display: grid;
  place-items: center;
  height: 56px;
  width: 56px;
  margin: 0 auto 12px;
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
  margin-top: 4px;
  font-size: var(--fs-sm);
  color: var(--c-muted);
}
.picker-loading,
.picker-empty {
  text-align: center;
  padding: 24px 0;
  color: var(--c-muted);
}
.picker-empty p {
  margin-top: 8px;
  font-size: var(--fs-sm);
}

.search-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border: 1px solid var(--c-border-strong);
  border-radius: var(--radius);
  background: var(--c-surface);
  color: var(--c-muted);
}
.search-input {
  flex: 1;
  border: none;
  background: transparent;
  padding: 12px 0;
  font-family: var(--font);
  font-size: var(--fs-body);
  color: var(--c-ink);
}
.search-input:focus {
  outline: none;
}

.b-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.b-item {
  display: flex;
  align-items: center;
  gap: 12px;
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

/* ---- tablet / iPad (≥768px) ----------------------------------------
   Lay the building list out as a comfortable 2-column grid instead of a
   single tall column, and give the hero a little more presence. The phone
   layout (single column) is untouched below this breakpoint. */
@media (min-width: 768px) {
  .b-list {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
  }
  .b-item {
    padding: 16px;
  }
  .picker-title {
    font-size: var(--fs-h1);
  }
}
</style>
