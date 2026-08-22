<script setup>
import { computed, inject, onBeforeUnmount, ref, watch } from "vue";
import { Button, ErrorMessage, createResource, toast } from "frappe-ui";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import { RouterLink, useRoute } from "vue-router";
import BuildingPicker from "../components/BuildingPicker.vue";
import { building } from "../building.js";
import { bedAssignmentTarget, housingCandidateFromQuery } from "../arrivalFlow.js";
import { floorLabel, statusLabel } from "../../../core/displayLabels.js";
import { safeErrorMessage } from "../../../core/errorMessage.js";

const route = useRoute();
const grid = createResource({
  url: "apex.habitat.api.front_desk.get_building_grid",
  makeParams: () => ({ building: building.value }),
});
const readiness = createResource({ url: "apex.habitat.api.front_desk.set_room_readiness" });
const error = ref("");
const canSetReadiness = (globalThis.window?.apex_portal?.capabilities || []).includes("set_readiness");
const rooms = computed(() => (grid.data?.floors || []).flatMap((floor) => floor.rooms.map((room) => ({ ...room, floor_label: floor.floor_label }))));
const candidate = computed(() => housingCandidateFromQuery(route.query));

const subscribeBuilding = inject("portalBuildingSubscribe", () => () => {});
let pollTimer;
let unsubscribers = [];
let liveBuilding = null;

function stopLive() {
  clearInterval(pollTimer);
  liveBuilding = null;
  while (unsubscribers.length) unsubscribers.pop()();
}

// Called on every building change, so it must be a no-op while the room already holds the
// current building — otherwise a poll tick would tear the listener down and rebuild it.
function startLive(name) {
  if (name === liveBuilding) return;
  liveBuilding = name;
  while (unsubscribers.length) unsubscribers.pop()();
  if (name) unsubscribers.push(subscribeBuilding(name, "doc_update", () => grid.fetch({ building: name })) || (() => {}));
  clearInterval(pollTimer);
  pollTimer = setInterval(() => building.value && grid.fetch({ building: building.value }), 10000);
}

watch(building, (value) => {
  if (value) grid.fetch();
  startLive(value);
}, { immediate: true });
onBeforeUnmount(stopLive);

async function setReady(room) {
  error.value = "";
  try {
    await readiness.submit({ room: room.room, status: "Ready" });
    toast.create({ type: "success", message: "الغرفة جاهزة" });
    await grid.fetch();
  } catch (exception) { error.value = safeErrorMessage(exception, "تعذر تحديث جاهزية الغرفة."); }
}
</script>

<template>
  <section class="feature-page">
    <header class="feature-page__header"><h2>الغرف والأسرّة</h2><BuildingPicker /></header>
    <article v-if="candidate" class="selected-resident" aria-live="polite">
      <div><span>اختر سريراً</span><strong dir="auto">{{ candidate.label }}</strong><small v-if="candidate.project" dir="auto">{{ candidate.project }}</small></div>
      <RouterLink to="/arrivals">تغيير العامل</RouterLink>
    </article>
    <PortalSkeleton v-if="grid.loading && !grid.data" :rows="3" label="جارٍ تحميل الأسرّة" />
    <ErrorMessage v-else-if="grid.error" message="تعذر تحميل الأسرّة." />
    <p v-else-if="!rooms.length && building" class="feature-page__empty">لا توجد غرف في هذا المبنى.</p>
    <section v-for="room in rooms" :key="room.room" class="feature-card room-card">
      <header>
        <div>
          <strong><bdi dir="auto" translate="no">{{ room.room_number }}</bdi></strong>
          <small>
            {{ floorLabel(room.floor_label) }} · {{ room.room_type || "غرفة" }} ·
            {{ room.current_occupancy || 0 }} من {{ room.bed_capacity || room.beds.length }} ·
            {{ statusLabel(room.readiness_status) }}
          </small>
          <small v-if="room.dominant_project" dir="auto">المشروع الغالب: {{ room.dominant_project }}</small>
        </div>
        <Button v-if="canSetReadiness && room.readiness_status !== 'Ready'" variant="subtle" :loading="readiness.loading" @click="setReady(room)">تأكيد الجاهزية</Button>
      </header>
      <div class="bed-grid">
        <component
          :is="candidate && bed.occupant ? 'div' : RouterLink"
          v-for="bed in room.beds"
          :key="bed.bed"
          :to="candidate && bed.occupant ? undefined : bedAssignmentTarget(bed.bed, candidate)"
          :aria-disabled="candidate && bed.occupant ? 'true' : undefined"
          :data-state="bed.bed_color"
        >
          <strong><bdi dir="auto" translate="no">{{ bed.bed_code || bed.bed }}</bdi></strong>
          <small v-if="bed.occupant" dir="auto">{{ bed.occupant.employee_name }}</small>
          <small v-else>{{ candidate ? 'اختر هذا السرير' : 'متاح' }}</small>
          <!-- An occupant's name is who is here, not why the tile refuses the tap the assignment
               flow just invited. With a candidate chosen the refusal has to say so itself. -->
          <small v-if="candidate && bed.occupant" class="bed-meta">مشغول، لا يقبل إسناداً</small>
          <small class="bed-meta">{{ statusLabel(bed.condition) }}<template v-if="bed.is_temporary"> · مؤقت</template></small>
        </component>
      </div>
    </section>
    <ErrorMessage v-if="error" :message="error" />
  </section>
</template>
