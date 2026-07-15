<!-- Copyright (c) 2026, AFMCO and contributors -->
<!--
  Housing supervisor console — ARCHETYPE 3 (Tablet Supervisor).
  Adopts the shared TabletSupervisorShell: dark side nav + KPI-tile row + a
  buildings-occupancy table / occupancy map + a requests-to-approve panel. One
  shared supervisor style across safety / housing / route; this domain is tinted
  by a subtle per-domain `accent` (housing = a slightly cooler Growth-Green).
  RTL-first, light + dark, all colour from the shared --c-* tokens only.
-->
<template>
  <TabletSupervisorShell
    :title="t('dash.title')"
    :subtitle="t('dash.subtitle')"
    :accent="accent"
    :menu-label="t('dash.menu')"
  >
    <template #brand>
      <span class="tsx-mark"><Icon name="building" :size="19" /></span>
      <span class="tsx-brand-txt">
        <b>{{ t("dash.brand") }}</b>
        <small>{{ t("dash.brandSub") }}</small>
      </span>
    </template>

    <template #nav>
      <a href="#" class="is-active"><Icon name="layout-grid" :size="18" />{{ t("dash.overview") }}</a>
      <span class="nav-label">{{ t("dash.navOps") }}</span>
      <a href="#"><Icon name="gauge" :size="18" />{{ t("dash.occupancy") }}</a>
      <a href="#"><Icon name="building" :size="18" />{{ t("dash.buildings") }}<span class="tsx-cnt">4</span></a>
      <a href="#"><Icon name="clipboard-check" :size="18" />{{ t("dash.inventory") }}</a>
      <a href="#"><Icon name="package" :size="18" />{{ t("dash.deliveries") }}<span class="tsx-cnt tsx-cnt-warn">3</span></a>
      <span class="nav-label">{{ t("dash.navMore") }}</span>
      <a href="#"><Icon name="chart-column" :size="18" />{{ t("dash.reports") }}</a>
      <a href="#"><Icon name="settings" :size="18" />{{ t("dash.settings") }}</a>
    </template>

    <template #title-actions>
      <span class="tsx-search"><Icon name="search" :size="15" />{{ t("dash.search") }}</span>
      <LangToggle />
      <span class="tsx-av">{{ t("dash.brand").slice(0, 1) }}</span>
    </template>

    <template #kpis>
      <div class="tsx-kpi">
        <div class="tsx-kt">{{ t("dash.kpiOccupancy") }}</div>
        <div class="tsx-kv tnum">87%</div>
        <div class="tsx-kd up"><Icon name="chart-column" :size="12" />{{ t("dash.kpiOccupancyDelta") }}</div>
        <svg class="tsx-spark" viewBox="0 0 100 26" preserveAspectRatio="none"><polyline points="0,14 20,15 40,10 60,12 80,7 100,6" /></svg>
      </div>
      <div class="tsx-kpi">
        <div class="tsx-kt">{{ t("dash.kpiVacant") }}</div>
        <div class="tsx-kv tnum">42</div>
        <div class="tsx-kd ok"><Icon name="check" :size="12" />{{ t("dash.kpiVacantDelta") }}</div>
        <svg class="tsx-spark tsx-spark-ok" viewBox="0 0 100 26" preserveAspectRatio="none"><polyline points="0,20 15,17 30,19 45,12 60,14 75,8 100,5" /></svg>
      </div>
      <div class="tsx-kpi">
        <div class="tsx-kt">{{ t("dash.kpiMaint") }}</div>
        <div class="tsx-kv tnum">6</div>
        <div class="tsx-kd warn"><Icon name="triangle-alert" :size="12" />{{ t("dash.kpiMaintDelta") }}</div>
        <svg class="tsx-spark tsx-spark-warn" viewBox="0 0 100 26" preserveAspectRatio="none"><polyline points="0,10 20,12 40,9 60,15 80,13 100,18" /></svg>
      </div>
      <div class="tsx-kpi">
        <div class="tsx-kt">{{ t("dash.kpiDeliveries") }}</div>
        <div class="tsx-kv tnum">3</div>
        <div class="tsx-kd warn"><Icon name="package" :size="12" />{{ t("dash.kpiDeliveriesDelta") }}</div>
        <svg class="tsx-spark tsx-spark-danger" viewBox="0 0 100 26" preserveAspectRatio="none"><polyline points="0,8 20,14 40,12 60,18 80,17 100,20" /></svg>
      </div>
    </template>

    <div class="tsx-split">
      <section class="tsx-panel">
        <header class="tsx-panel-h">
          <b>{{ t("dash.buildingsOccupancy") }}</b>
          <span class="tsx-live"><span class="tsx-dot"></span>{{ t("dash.live") }}</span>
        </header>
        <div class="tsx-tbl-wrap">
          <table class="tsx-tbl">
            <thead>
              <tr>
                <th>{{ t("dash.colBuilding") }}</th>
                <th>{{ t("dash.colBeds") }}</th>
                <th>{{ t("dash.colOccupancy") }}</th>
                <th>{{ t("dash.colStatus") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in rows" :key="i">
                <td>
                  <div class="tsx-who">
                    <span class="tsx-who-a"><Icon name="building" :size="14" /></span>
                    <div><b>{{ r.building }}</b></div>
                  </div>
                </td>
                <td class="tnum">{{ r.beds }}</td>
                <td class="tnum">{{ r.occ }}</td>
                <td><span class="tsx-badge" :class="'b-' + r.status">{{ r.label }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="tsx-map">
          <div class="tsx-map-cap"><Icon name="gauge" :size="13" />{{ t("dash.occupancyMap") }}</div>
          <svg class="tsx-map-svg" viewBox="0 0 400 150" preserveAspectRatio="none">
            <rect width="400" height="150" fill="var(--c-surface)" />
            <path d="M0 40 H400 M0 90 H400 M120 0 V150 M280 0 V150" stroke="var(--c-border)" stroke-width="1" />
            <path d="M40 120 C120 100 160 70 220 60 S320 30 380 34" fill="none" stroke="var(--ts-accent)" stroke-width="3" stroke-linecap="round" />
            <circle cx="40" cy="120" r="6" fill="var(--ts-accent)" /><circle cx="40" cy="120" r="11" fill="var(--ts-accent)" opacity=".18" />
            <circle cx="220" cy="60" r="5" fill="var(--c-mint)" />
            <circle cx="380" cy="34" r="6" fill="var(--c-warning)" />
          </svg>
        </div>
      </section>

      <section class="tsx-panel tsx-appr">
        <header class="tsx-panel-h">
          <b>{{ t("dash.requestsQueue") }}</b>
          <span class="tsx-pill-count tnum">{{ requests.length }}</span>
        </header>
        <div v-for="(a, i) in requests" :key="i" class="tsx-appr-item">
          <div class="tsx-appr-top">
            <span class="tsx-who-a" :class="'a-' + a.sev">{{ a.init }}</span>
            <b>{{ a.title }}</b>
            <span class="tsx-req tnum">{{ a.ago }}</span>
          </div>
          <div class="tsx-appr-desc">{{ a.meta }}</div>
          <div class="tsx-appr-btns">
            <button type="button" class="tsx-sbtn tsx-sbtn-ok">{{ t("dash.approve") }}</button>
            <button type="button" class="tsx-sbtn tsx-sbtn-no">{{ t("dash.reject") }}</button>
          </div>
        </div>
      </section>
    </div>
  </TabletSupervisorShell>
</template>

<script setup>
import { computed, watch } from "vue";
// Direct-path shell import: the barrel @shared/components also re-exports
// BuildingPicker (which pulls portal-specific i18n exports), so import the shell
// file directly to keep this portal's build independent of the barrel.
import TabletSupervisorShell from "@shared/components/TabletSupervisorShell.vue";
import Icon from "./components/Icon.vue";
import LangToggle from "@shared/components/LangToggle.vue";
import { useI18n } from "./i18n";

const { t, tData, dir } = useI18n();

// Per-domain accent (kept inside the Growth-Green family). Housing = a slightly
// cooler / teal-leaning green so it reads as the same system, one step apart.
const accent = "#0d8f66";

const rows = computed(() => tData("dash.building_rows") || []);
const requests = computed(() => tData("dash.request_rows") || []);

watch(
  dir,
  (d) => {
    document.documentElement.setAttribute("dir", d);
    document.documentElement.setAttribute("lang", d === "rtl" ? "ar" : "en");
  },
  { immediate: true },
);
</script>

<style scoped>
.tnum {
  font-variant-numeric: tabular-nums;
  font-family: var(--font-num);
}

/* ---- brand (side-nav top) ---- */
.tsx-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: var(--radius-sm);
  background: linear-gradient(150deg, var(--c-mint), var(--ts-accent, var(--c-primary)));
  color: var(--c-header-bg);
  flex: 0 0 auto;
}
.tsx-brand-txt b {
  display: block;
  font-size: var(--fs-h3);
  font-weight: var(--fw-heading);
  line-height: 1.1;
}
.tsx-brand-txt small {
  font-size: var(--fs-xs);
  opacity: 0.7;
}

/* ---- nav count badges ---- */
.tsx-cnt {
  margin-inline-start: auto;
  font-size: var(--fs-xs);
  font-weight: var(--fw-heading);
  background: color-mix(in srgb, var(--c-header-ink) 16%, transparent);
  color: var(--c-header-ink);
  border-radius: var(--radius-pill);
  padding: 1px 8px;
}
.tsx-cnt-warn {
  background: var(--c-warning);
  color: #3a2708;
}

/* ---- top-bar actions ---- */
.tsx-search {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: var(--c-surface-2);
  border: var(--border-width) solid var(--c-border);
  border-radius: var(--radius-pill);
  padding: 8px 14px;
  font-size: var(--fs-sm);
  color: var(--c-muted);
  min-width: 150px;
}
.tsx-av {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--ts-accent, var(--c-primary));
  color: #fff;
  font-weight: var(--fw-heading);
  font-size: var(--fs-sm);
  flex: 0 0 auto;
}

/* ---- KPI tiles ---- */
.tsx-kpi {
  background: var(--c-surface-2);
  border: var(--border-width) solid var(--c-border);
  border-radius: var(--radius);
  padding: 14px 15px;
  box-shadow: var(--shadow-sm);
}
.tsx-kt {
  font-size: var(--fs-sm);
  color: var(--c-muted);
  font-weight: var(--fw-semibold);
}
.tsx-kv {
  font-size: 27px;
  font-weight: var(--fw-heading);
  letter-spacing: -0.02em;
  line-height: 1.15;
  margin-top: 2px;
}
.tsx-kd {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--fs-xs);
  font-weight: var(--fw-heading);
  margin-top: 3px;
}
.tsx-kd.up,
.tsx-kd.ok {
  color: var(--c-success);
}
.tsx-kd.warn {
  color: var(--c-warning);
}
.tsx-kd.down {
  color: var(--c-danger);
}
.tsx-spark {
  display: block;
  width: 100%;
  height: 26px;
  margin-top: 8px;
}
.tsx-spark polyline {
  fill: none;
  stroke: var(--ts-accent, var(--c-primary));
  stroke-width: 2;
}
.tsx-spark-ok polyline {
  stroke: var(--c-success);
}
.tsx-spark-warn polyline {
  stroke: var(--c-warning);
}
.tsx-spark-danger polyline {
  stroke: var(--c-danger);
}

/* ---- split + panels ---- */
.tsx-split {
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: 16px;
}
@media (max-width: 900px) {
  .tsx-split {
    grid-template-columns: 1fr;
  }
}
.tsx-panel {
  background: var(--c-surface-2);
  border: var(--border-width) solid var(--c-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}
.tsx-panel-h {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: var(--border-width) solid var(--c-border);
}
.tsx-panel-h b {
  font-size: var(--fs-h3);
  font-weight: var(--fw-heading);
}
.tsx-live {
  margin-inline-start: auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-xs);
  font-weight: var(--fw-heading);
  color: var(--c-success);
}
.tsx-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--c-success);
  animation: tsxpulse 1.8s infinite;
}
@keyframes tsxpulse {
  0% {
    box-shadow: 0 0 0 0 color-mix(in srgb, var(--c-success) 55%, transparent);
  }
  70% {
    box-shadow: 0 0 0 6px transparent;
  }
  100% {
    box-shadow: 0 0 0 0 transparent;
  }
}
.tsx-pill-count {
  margin-inline-start: auto;
  font-size: var(--fs-xs);
  font-weight: var(--fw-heading);
  background: var(--c-warning-bg);
  color: var(--c-warning);
  padding: 2px 9px;
  border-radius: var(--radius-pill);
}

/* ---- table ---- */
.tsx-tbl-wrap {
  overflow-x: auto;
}
.tsx-tbl {
  width: 100%;
  border-collapse: collapse;
  min-width: 420px;
}
.tsx-tbl th {
  text-align: start;
  font-size: var(--fs-xs);
  font-weight: var(--fw-heading);
  letter-spacing: 0.05em;
  color: var(--c-muted);
  padding: 10px 14px;
  border-bottom: var(--border-width) solid var(--c-border);
}
.tsx-tbl td {
  padding: 12px 14px;
  font-size: var(--fs-sm);
  border-bottom: var(--border-width) solid var(--c-border);
}
.tsx-tbl tr:last-child td {
  border-bottom: 0;
}
.tsx-who {
  display: flex;
  align-items: center;
  gap: 9px;
}
.tsx-who-a {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--ts-accent, var(--c-primary)) 16%, transparent);
  color: var(--ts-accent, var(--c-primary));
  font-weight: var(--fw-heading);
  font-size: var(--fs-xs);
  flex: 0 0 auto;
}
.tsx-who b {
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
}
.tsx-who small {
  display: block;
  color: var(--c-muted);
  font-size: var(--fs-xs);
}
.tsx-badge {
  display: inline-flex;
  align-items: center;
  font-size: var(--fs-xs);
  font-weight: var(--fw-heading);
  padding: 3px 10px;
  border-radius: var(--radius-pill);
}
.b-run {
  background: var(--c-info-bg);
  color: var(--c-info);
}
.b-ok {
  background: var(--c-success-bg);
  color: var(--c-success);
}
.b-late {
  background: var(--c-warning-bg);
  color: var(--c-warning);
}

/* ---- mini map ---- */
.tsx-map {
  padding: 14px 16px 16px;
}
.tsx-map-cap {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-xs);
  font-weight: var(--fw-heading);
  color: var(--c-muted);
  margin-bottom: 8px;
}
.tsx-map-svg {
  width: 100%;
  height: 150px;
  display: block;
  border-radius: var(--radius);
  border: var(--border-width) solid var(--c-border);
}

/* ---- approvals panel ---- */
.tsx-appr-item {
  padding: 13px 16px;
  border-bottom: var(--border-width) solid var(--c-border);
}
.tsx-appr-item:last-child {
  border-bottom: 0;
}
.tsx-appr-top {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 8px;
}
.tsx-appr-top b {
  font-size: var(--fs-sm);
  font-weight: var(--fw-semibold);
}
.a-danger {
  background: var(--c-danger-bg);
  color: var(--c-danger);
}
.a-warn {
  background: var(--c-warning-bg);
  color: var(--c-warning);
}
.a-info {
  background: var(--c-info-bg);
  color: var(--c-info);
}
.tsx-req {
  margin-inline-start: auto;
  font-size: var(--fs-xs);
  color: var(--c-muted);
}
.tsx-appr-desc {
  font-size: var(--fs-sm);
  color: var(--c-ink-soft);
  margin-bottom: 11px;
}
.tsx-appr-btns {
  display: flex;
  gap: 8px;
}
.tsx-sbtn {
  flex: 1;
  padding: 9px;
  border-radius: var(--radius-sm);
  font-family: var(--font);
  font-size: var(--fs-sm);
  font-weight: var(--fw-heading);
  border: var(--border-width) solid transparent;
  cursor: pointer;
}
.tsx-sbtn-ok {
  background: var(--ts-accent, var(--c-primary));
  color: #fff;
}
.tsx-sbtn-no {
  background: transparent;
  color: var(--c-danger);
  border-color: color-mix(in srgb, var(--c-danger) 40%, transparent);
}
</style>
