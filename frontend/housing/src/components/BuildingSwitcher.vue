<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="switcher">
    <div class="switcher-hero">
      <div class="switcher-mark"><Icon name="building" :size="26" /></div>
      <h2 class="section-title">{{ t("building.title") }}</h2>
      <p class="section-sub">{{ t("building.subtitle") }}</p>
    </div>

    <PageShell
      :state="pickerState"
      :loading-label="t('common.loading')"
      :skeleton-rows="4"
      :error-title="t('errors.gridFailed')"
      :error-detail="listErrorMessage"
      :empty-title="t('building.empty')"
      :empty-hint="scopeHint"
      @retry="listRes.reload()"
    >
      <template #empty-icon><Icon name="building" :size="24" /></template>

      <section v-for="group in grouped" :key="group.key" class="switcher-group">
        <h3 class="switcher-site">{{ group.title }}</h3>
        <ul class="switcher-list">
          <li v-for="b in group.buildings" :key="b.building">
            <button
              type="button"
              class="switcher-item"
              :class="{ 'is-empty': !b.has_rooms }"
              @click="$emit('select', b.building, b.building_title)"
            >
              <span class="switcher-icon"><Icon name="building" :size="18" /></span>
              <span class="switcher-body">
                <span class="switcher-name">
                  {{ b.building_title }}
                  <Badge
                    v-if="b.accommodation_type"
                    theme="gray"
                    size="sm"
                    :label="tEnum('accommodationType', b.accommodation_type)"
                  />
                </span>
                <span class="switcher-mix">
                  {{
                    b.has_rooms
                      ? t("beds.summary", { occupied: b.occupied, total: b.total_beds })
                      : t("building.noRooms")
                  }}
                </span>
              </span>
              <Badge
                v-if="b.has_rooms"
                :theme="mixTheme(b)"
                size="lg"
                :label="b.occupancy_pct + '%'"
              />
              <Badge v-else theme="orange" size="lg" :label="t('building.noRoomsBadge')" />
            </button>
          </li>
        </ul>
      </section>
    </PageShell>
  </div>
</template>

<script setup>
import { computed, watch } from "vue";
import { Badge, createResource } from "frappe-ui";
import Icon from "./Icon.vue";
import PageShell from "./PageShell.vue";
import { useI18n, resourceErrorMessage } from "../i18n";

const emit = defineEmits(["select"]);
const { t, tEnum } = useI18n();

const listRes = createResource({
  url: "apex.habitat.api.front_desk.list_supervisor_buildings",
  auto: true,
  onSuccess: (rows) => {
    if (Array.isArray(rows) && rows.length === 1 && rows[0].auto) {
      emit("select", rows[0].building, rows[0].building_title);
    }
  },
});

const scopeRes = createResource({
  url: "apex.habitat.api.front_desk.get_buildings_scope_state",
});

const buildings = computed(() => listRes.data || []);
const listErrorMessage = computed(() => resourceErrorMessage(listRes.error, "errors.gridFailed"));

const pickerState = computed(() => {
  if (listRes.loading && !buildings.value.length) return "loading";
  if (listRes.error) return "error";
  if (!buildings.value.length) return "empty";
  return "ready";
});

const grouped = computed(() => {
  const groups = new Map();
  for (const b of buildings.value) {
    const key = b.site || "";
    if (!groups.has(key)) {
      groups.set(key, {
        key: key || "__unsited",
        title: b.site_title || t("building.noSite"),
        buildings: [],
      });
    }
    groups.get(key).buildings.push(b);
  }
  return [...groups.values()];
});

const scopeHint = computed(() => {
  if (scopeRes.error) return t("errors.scopeUnknown");
  const state = scopeRes.data;
  if (!state) return "";
  if (state.is_scoped && !state.active_buildings) return t("beds.emptyScoped");
  if (!state.active_buildings) return t("beds.emptyNoActive");
  return "";
});

function mixTheme(b) {
  if (b.occupancy_pct >= 95) return "red";
  if (b.occupancy_pct >= 80) return "orange";
  return "green";
}

watch(
  () => listRes.data,
  (rows) => {
    if (Array.isArray(rows) && !rows.length) scopeRes.fetch();
  },
);
</script>

<style scoped>
.switcher {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.switcher-hero {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: var(--sp-1) var(--sp-3);
  padding-block: var(--sp-3) var(--sp-5);
  text-align: start;
}
.switcher-mark {
  display: grid;
  place-items: center;
  grid-row: 1 / span 2;
  block-size: 56px;
  inline-size: 56px;
  border-radius: var(--radius-sm);
  color: var(--c-primary);
  background: color-mix(in srgb, var(--c-primary) 12%, transparent);
}
.switcher-hero .section-title,
.switcher-hero .section-sub {
  margin: 0;
}
.switcher-group + .switcher-group {
  margin-block-start: var(--sp-5);
}
.switcher-site {
  margin-block-end: var(--sp-2);
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
  color: var(--c-muted);
  letter-spacing: 0.02em;
}
.switcher-item.is-empty .switcher-name,
.switcher-item.is-empty .switcher-mix {
  color: var(--c-muted);
}
.switcher-list {
  display: grid;
  gap: var(--sp-3);
  margin: 0;
  padding: 0;
  list-style: none;
}
.switcher-item {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  inline-size: 100%;
  min-block-size: 76px;
  padding: var(--sp-3) var(--sp-4);
  border: var(--border-width) solid var(--c-border);
  border-radius: var(--radius);
  background: var(--c-surface-2);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  text-align: start;
}
@media (hover: hover) {
  .switcher-item:hover {
    border-color: var(--c-primary);
  }
}
.switcher-icon {
  display: grid;
  place-items: center;
  block-size: 36px;
  inline-size: 36px;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
  color: var(--c-primary);
  background: color-mix(in srgb, var(--c-primary) 10%, transparent);
}
.switcher-body {
  flex: 1;
  min-inline-size: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.switcher-name {
  font-size: var(--fs-body);
  font-weight: var(--fw-semibold);
  color: var(--c-ink);
}
.switcher-mix {
  font-size: var(--fs-xs);
  color: var(--c-muted);
}
@container mc-frame (min-width: 34rem) {
  .switcher-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
