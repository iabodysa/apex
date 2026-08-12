<script setup>
import { computed, ref, watch } from "vue";
import { Button, ErrorMessage, LoadingIndicator, createResource, toast } from "frappe-ui";
import BuildingPicker from "../components/BuildingPicker.vue";
import { building } from "../building.js";

const grid = createResource({
  url: "apex.habitat.api.front_desk.get_building_grid",
  makeParams: () => ({ building: building.value }),
});
const readiness = createResource({ url: "apex.habitat.api.front_desk.set_room_readiness" });
const error = ref("");
const canSetReadiness = (globalThis.window?.apex_portal?.capabilities || []).includes("set_readiness");
const rooms = computed(() => (grid.data?.floors || []).flatMap((floor) => floor.rooms.map((room) => ({ ...room, floor_label: floor.floor_label }))));
watch(building, (value) => value && grid.fetch(), { immediate: true });
async function setReady(room) {
  error.value = "";
  try {
    await readiness.submit({ room: room.room, status: "Ready" });
    toast.create({ type: "success", message: "الغرفة جاهزة" });
    await grid.fetch();
  } catch (exception) { error.value = exception.message || "تعذر تحديث جاهزية الغرفة."; }
}
</script>

<template>
  <section class="feature-page">
    <header class="feature-page__header"><h2>الغرف والأسرّة</h2><BuildingPicker /></header>
    <LoadingIndicator v-if="grid.loading" aria-label="جارٍ تحميل الأسرّة" />
    <ErrorMessage v-else-if="grid.error" message="تعذر تحميل الأسرّة." />
    <p v-else-if="!rooms.length && building" class="feature-page__empty">لا توجد غرف في هذا المبنى.</p>
    <section v-for="room in rooms" :key="room.room" class="feature-card room-card">
      <header>
        <div><strong>{{ room.room_number }}</strong><small>{{ room.floor_label }} · {{ room.readiness_status }}</small></div>
        <Button v-if="canSetReadiness && room.readiness_status !== 'Ready'" variant="subtle" :loading="readiness.loading" @click="setReady(room)">تأكيد الجاهزية</Button>
      </header>
      <div class="bed-grid">
        <RouterLink v-for="bed in room.beds" :key="bed.bed" :to="`/beds/${bed.bed}`" :data-state="bed.bed_color">
          <strong>{{ bed.bed_code || bed.bed }}</strong>
          <small v-if="bed.occupant" dir="auto">{{ bed.occupant.employee_name }}</small>
          <small v-else>متاح</small>
        </RouterLink>
      </div>
    </section>
    <ErrorMessage v-if="error" :message="error" />
  </section>
</template>
