<script setup>
import { inject, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { Button, FormControl } from "frappe-ui";
import { createLeafletAdapter } from "./leafletAdapter.js";
import { createTransportMapState } from "./transportMapState.js";
import "./styles.css";

const gateway = inject("transportSupervisorGateway", null);
const mapRoot = ref(null);
const mapState = createTransportMapState();
const mapAdapter = createLeafletAdapter();
const { phase: state, error, project, status, projects, statuses, visible } = mapState;

async function draw() {
  if (!mapRoot.value || state.value !== "ready") return;
  try {
    await mapAdapter.draw(mapRoot.value, visible.value);
  } catch (reason) {
    mapState.fail(reason);
  }
}

async function load() {
  await mapState.load(() => gateway.map());
  await nextTick();
  await draw();
}

async function applyFilters() { await nextTick(); await draw(); }

onMounted(load);
onBeforeUnmount(mapAdapter.destroy);
</script>

<template>
  <section class="feature-page transport-map-page" :aria-busy="state === 'loading'">
    <header class="feature-page__heading">
      <div><p class="feature-page__eyebrow">تشغيل النقل</p><h2>الخريطة المباشرة</h2><p>مواقع السائقين ومسارات الرحلات المسندة إليك.</p></div>
      <Button variant="outline" icon="refresh-cw" label="تحديث" @click="load" />
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
