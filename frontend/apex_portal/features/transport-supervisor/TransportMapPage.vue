<script setup>
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { Button, FormControl } from "frappe-ui";

const gateway = inject("transportSupervisorGateway", null);
const state = ref("loading");
const error = ref("");
const positions = ref([]);
const project = ref("");
const status = ref("");
const mapRoot = ref(null);
let map;
let layer;

const projects = computed(() => [...new Set(positions.value.map((item) => item.project).filter(Boolean))]);
const statuses = computed(() => [...new Set(positions.value.map((item) => item.status).filter(Boolean))]);
const visible = computed(() => positions.value.filter((item) =>
  (!project.value || item.project === project.value) && (!status.value || item.status === status.value),
));

function loadStyle() {
  if (document.querySelector("link[data-apex-leaflet]")) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = "/assets/apex/vendor/leaflet-1.9.4/leaflet.css";
  link.dataset.apexLeaflet = "";
  document.head.append(link);
}

function loadLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  const existing = document.querySelector("script[data-apex-leaflet]");
  if (existing) return new Promise((resolve, reject) => {
    existing.addEventListener("load", () => resolve(window.L), { once: true });
    existing.addEventListener("error", reject, { once: true });
  });
  loadStyle();
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "/assets/apex/vendor/leaflet-1.9.4/leaflet.js";
    script.dataset.apexLeaflet = "";
    script.onload = () => resolve(window.L);
    script.onerror = () => reject(new Error("تعذّر تحميل الخريطة."));
    document.head.append(script);
  });
}

function coordinates(item) {
  return (item.path || []).map((point) => Array.isArray(point)
    ? [Number(point[0]), Number(point[1])]
    : [Number(point.lat), Number(point.lng)]).filter(([lat, lng]) => Number.isFinite(lat) && Number.isFinite(lng));
}

async function draw() {
  if (!mapRoot.value || state.value !== "ready") return;
  const L = await loadLeaflet();
  if (!map) {
    map = L.map(mapRoot.value, { zoomControl: true }).setView([24.7136, 46.6753], 6);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "© OpenStreetMap",
      crossOrigin: true,
    }).addTo(map);
    layer = L.layerGroup().addTo(map);
  }
  layer.clearLayers();
  const bounds = [];
  for (const item of visible.value) {
    const route = coordinates(item);
    if (route.length > 1) L.polyline(route, { color: "#079455", weight: 4, opacity: 0.8 }).addTo(layer);
    for (const stop of item.stops || []) {
      const point = [Number(stop.lat), Number(stop.lng)];
      if (point.every(Number.isFinite)) {
        L.circleMarker(point, { radius: 5, color: "#07583a", fillColor: "#f5efe2", fillOpacity: 1 }).bindTooltip(stop.stop_name || "نقطة توقف").addTo(layer);
        bounds.push(point);
      }
    }
    const driver = [Number(item.lat), Number(item.lng)];
    if (item.has_position && driver.every(Number.isFinite)) {
      const popup = document.createElement("div");
      const driverName = document.createElement("strong");
      driverName.textContent = item.driver_name || "السائق";
      const plate = document.createElement("span");
      plate.textContent = item.plate || "";
      popup.append(driverName, document.createElement("br"), plate);
      L.circleMarker(driver, { radius: 9, color: "#ffffff", weight: 3, fillColor: item.stale ? "#b54708" : "#079455", fillOpacity: 1 })
        .bindPopup(popup)
        .addTo(layer);
      bounds.push(driver);
    }
    bounds.push(...route);
  }
  if (bounds.length) map.fitBounds(bounds, { padding: [32, 32], maxZoom: 16 });
  else map.setView([24.7136, 46.6753], 6);
  map.invalidateSize();
}

async function load() {
  state.value = "loading";
  error.value = "";
  try {
    const result = await gateway.map();
    positions.value = result?.positions || [];
    state.value = positions.value.length ? "ready" : "empty";
    await nextTick();
    await draw();
  } catch (reason) {
    state.value = reason?.status === 403 ? "denied" : "error";
    error.value = reason?.message || "تعذّر تحميل حركة المركبات.";
  }
}

async function applyFilters() { await nextTick(); await draw(); }

onMounted(load);
onBeforeUnmount(() => { map?.remove(); map = null; });
</script>

<template>
  <section class="feature-page transport-map-page" :aria-busy="state === 'loading'">
    <header class="feature-page__heading">
      <div><p class="feature-page__eyebrow">تشغيل النقل</p><h2>الخريطة المباشرة</h2><p>مواقع السائقين ومسارات الرحلات المسندة إليك.</p></div>
      <Button variant="outline" icon="refresh-cw" @click="load">تحديث</Button>
    </header>
    <div v-if="state === 'loading'" class="feature-state" role="status">جارٍ تحديث الخريطة…</div>
    <div v-else-if="state === 'denied'" class="feature-state">لا تملك صلاحية هذه الرحلات.</div>
    <div v-else-if="state === 'error'" class="feature-state feature-state--error"><p role="alert">{{ error }}</p><Button variant="outline" @click="load">إعادة المحاولة</Button></div>
    <div v-else-if="state === 'empty'" class="feature-state">لا توجد رحلات نشطة الآن.</div>
    <template v-else>
      <div class="transport-map-filters">
        <FormControl v-model="project" type="select" label="المشروع" :options="[{ label: 'كل المشاريع', value: '' }, ...projects.map((value) => ({ label: value, value }))]" @change="applyFilters" />
        <FormControl v-model="status" type="select" label="الحالة" :options="[{ label: 'كل الحالات', value: '' }, ...statuses.map((value) => ({ label: value, value }))]" @change="applyFilters" />
      </div>
      <div ref="mapRoot" class="transport-map" aria-label="خريطة حركة المركبات" />
      <div class="transport-map-list" aria-live="polite">
        <article v-for="item in visible" :key="item.dispatch_trip" class="feature-card">
          <div><strong>{{ item.route_name || item.route_plan }}</strong><span>{{ item.driver_name || 'لم يحدد السائق' }} · {{ item.plate || 'لم تحدد المركبة' }}</span></div>
          <span>{{ item.stale ? 'الموقع قديم' : item.has_position ? 'مباشر' : 'لا يوجد موقع' }}</span>
        </article>
      </div>
    </template>
  </section>
</template>

<style scoped>
.transport-map-filters { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--sp-4); margin-block-end: var(--sp-4); }
.transport-map { min-height: 460px; border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; background: var(--surface); }
.transport-map-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--sp-3); margin-block-start: var(--sp-4); }
@media (max-width: 640px) { .transport-map-filters, .transport-map-list { grid-template-columns: 1fr; } .transport-map { min-height: 360px; } }
</style>
