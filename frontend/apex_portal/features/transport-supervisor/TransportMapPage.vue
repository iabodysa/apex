<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { Button, FormControl, createResource } from "frappe-ui";
import { statusLabel } from "../../core/displayLabels.js";
import { createLeafletAdapter } from "./leafletAdapter.js";
import { createTransportMapState, selectedMapRows } from "./transportMapState.js";
import "./styles.css";

const positions = createResource({
  url: "apex.salis.api.route_supervisor.get_active_driver_positions",
  method: "GET",
  auto: false,
});
const mapRoot = ref(null);
const mapState = createTransportMapState();
const mapAdapter = createLeafletAdapter();
const { phase: state, error, project, status, projects, statuses, visible } = mapState;
const selectedTrip = ref("");
const selected = computed(() => visible.value.find((item) => item.dispatch_trip === selectedTrip.value) || visible.value[0] || null);

async function draw() {
  if (!mapRoot.value || state.value !== "ready") return;
  try {
    await mapAdapter.draw(mapRoot.value, selectedMapRows(visible.value, selectedTrip.value));
  } catch (reason) {
    mapState.fail(reason);
  }
}

async function load() {
  await mapState.load(() => positions.fetch());
  if (!visible.value.some((item) => item.dispatch_trip === selectedTrip.value)) {
    selectedTrip.value = visible.value[0]?.dispatch_trip || "";
  }
  await nextTick();
  await draw();
}

async function applyFilters() {
  if (!visible.value.some((item) => item.dispatch_trip === selectedTrip.value)) {
    selectedTrip.value = visible.value[0]?.dispatch_trip || "";
  }
  await nextTick();
  await draw();
}

onMounted(load);
onBeforeUnmount(mapAdapter.destroy);
</script>

<template>
  <section class="feature-page transport-map-page" :aria-busy="state === 'loading'">
    <header class="feature-page__heading">
      <div>
        <p class="feature-page__eyebrow">تشغيل النقل</p>
        <h2>الخريطة المباشرة</h2>
        <p>مواقع السائقين ومسارات الرحلات المسندة إليك.</p>
      </div>
      <Button variant="outline" icon-left="refresh-cw" @click="load">تحديث</Button>
    </header>
    <div v-if="state === 'loading'" class="feature-state" role="status">جارٍ تحديث الخريطة…</div>
    <div v-else-if="state === 'denied'" class="feature-state">لا تملك صلاحية هذه الرحلات.</div>
    <div v-else-if="state === 'error'" class="feature-state feature-state--error">
      <p role="alert">{{ error }}</p>
      <Button variant="outline" @click="load">إعادة المحاولة</Button>
    </div>
    <div v-else-if="state === 'empty'" class="feature-state">لا توجد رحلات نشطة الآن.</div>
    <template v-else>
      <div class="transport-map-filters">
        <FormControl v-model="project" type="select" label="المشروع" :options="[{ label: 'كل المشاريع', value: '' }, ...projects.map((value) => ({ label: value, value }))]" @change="applyFilters" />
        <FormControl v-model="status" type="select" label="الحالة" :options="[{ label: 'كل الحالات', value: '' }, ...statuses.map((value) => ({ label: statusLabel(value), value }))]" @change="applyFilters" />
      </div>
      <ul class="transport-map-legend" aria-label="دليل الخريطة">
        <li data-kind="route">مسار الرحلة</li>
        <li data-kind="live">موقع مباشر</li>
        <li data-kind="stale">موقع متأخر</li>
        <li data-kind="stop">نقطة توقف</li>
      </ul>
      <div ref="mapRoot" class="transport-map" aria-label="خريطة حركة المركبات" />
      <article v-if="selected" class="transport-map-selection">
        <div class="record-identity">
          <span>الرحلة المحددة</span>
          <strong dir="auto">{{ selected.route_name || "رحلة تشغيل" }}</strong>
          <bdi class="record-reference" dir="auto" translate="no">{{ selected.dispatch_trip }}</bdi>
        </div>
        <dl>
          <div><dt>السائق</dt><dd>{{ selected.driver_name || "غير مسند" }}</dd></div>
          <div><dt>المركبة</dt><dd><bdi dir="auto" translate="no">{{ selected.plate || "غير مسندة" }}</bdi></dd></div>
          <div><dt>المشروع</dt><dd dir="auto">{{ selected.project || "غير محدد" }}</dd></div>
        </dl>
        <RouterLink class="transport-map-selection__action" :to="`/trips/${selected.dispatch_trip}`">فتح تشغيل الرحلة</RouterLink>
      </article>
      <div class="transport-map-list" aria-live="polite">
        <button v-for="item in visible" :key="item.dispatch_trip" type="button" class="feature-card transport-map-card" :aria-pressed="item.dispatch_trip === selected?.dispatch_trip" @click="selectedTrip = item.dispatch_trip">
          <div>
            <strong>{{ item.route_name || item.route_plan }}</strong>
            <span>{{ item.driver_name || "لم يحدد السائق" }} · <bdi dir="auto" translate="no">{{ item.plate || "لم تحدد المركبة" }}</bdi></span>
          </div>
          <span class="transport-map-status" :data-state="item.stale ? 'stale' : item.has_position ? 'live' : 'offline'">{{ item.stale ? "آخر موقع متأخر" : item.has_position ? "مباشر" : "لا يوجد موقع" }}</span>
        </button>
      </div>
    </template>
  </section>
</template>
