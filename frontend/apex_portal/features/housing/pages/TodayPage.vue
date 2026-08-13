<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { ErrorMessage, LoadingIndicator, createResource } from "frappe-ui";
import BuildingPicker from "../components/BuildingPicker.vue";
import { building } from "../building.js";
import { createSupervisorBuildingsResource } from "../data/buildings.js";
import PortalErrorState from "../../../components/PortalErrorState.vue";

const capabilities = globalThis.window?.apex_portal?.capabilities || [];
const canSeeBeds = capabilities.includes("estate_read");
const canSeeArrivals = capabilities.includes("check_in");
const canSeeMaintenance = capabilities.includes("maintenance_read");
const canCreateMaintenance = capabilities.includes("maintenance_create");
const canSeeCustody = capabilities.includes("custody_read");
const canSeeSafety = capabilities.includes("safety_read");
const canSeePortfolio = canSeeBeds;
const buildings = createSupervisorBuildingsResource();
const grid = createResource({ url: "apex.habitat.api.front_desk.get_building_grid" });
const requests = createResource({ url: "apex.habitat.api.front_desk.building_open_requests" });
const arrivals = createResource({ url: "apex.habitat.api.arrivals_desk.get_expected_arrivals" });
const safety = createResource({ url: "apex.habitat.api.safety_checklist.get_due_cadences" });
const error = ref("");
const visibleResources = computed(() => [
  canSeeBeds ? grid : null,
  canSeeMaintenance ? requests : null,
  canSeeArrivals ? arrivals : null,
  canSeeSafety ? safety : null,
].filter(Boolean));
const loading = computed(() => visibleResources.value.some((resource) => resource.loading));
const summary = computed(() => grid.data?.summary || {});
const availableBeds = computed(() => Number(summary.value.available || 0));
const occupiedBeds = computed(() => Number(summary.value.occupied || 0));
const unavailableBeds = computed(() => ["blocked", "out_of_service"]
  .reduce((total, key) => total + Number(summary.value[key] || 0), 0));
const dueRounds = computed(() => safety.data?.due?.length || 0);

function selectBuilding(name) {
  building.value = name;
}

async function load() {
  error.value = "";
  if (!building.value) return;
  const jobs = [];
  if (canSeeBeds) jobs.push(grid.fetch({ building: building.value }));
  if (canSeeMaintenance) jobs.push(requests.fetch({ building: building.value }));
  if (canSeeArrivals) jobs.push(arrivals.fetch({ building: building.value }));
  if (canSeeSafety) jobs.push(safety.fetch({ building: building.value }));
  const results = await Promise.allSettled(jobs);
  if (results.some((result) => result.status === "rejected")) {
    error.value = "تعذّر تحديث جزء من لوحة اليوم. يمكنك متابعة بقية الأعمال الظاهرة.";
  }
}

watch(building, load, { immediate: true });
onMounted(() => {
  if (canSeePortfolio) buildings.fetch();
});
</script>
<template>
  <section class="feature-page today-page">
    <header class="feature-page__header arrivals-heading">
      <div><p class="feature-kicker">وردية السكن</p><h2>ما يحتاج انتباهك اليوم</h2><p>صورة سريعة للمبنى، ثم أقرب إجراء.</p></div>
      <BuildingPicker v-if="canSeePortfolio" :resource="buildings" />
    </header>

    <section v-if="canSeePortfolio" class="today-portfolio" aria-labelledby="today-portfolio-title">
      <header>
        <div><p class="feature-kicker">نطاق الإشراف</p><h3 id="today-portfolio-title">جاهزية مباني السكن</h3></div>
        <RouterLink to="/beds">فتح لوحة الغرف</RouterLink>
      </header>
      <LoadingIndicator v-if="buildings.loading && !buildings.data" aria-label="جارٍ تحميل مباني السكن" />
      <PortalErrorState
        v-else-if="buildings.error"
        title="تعذّر تحميل نطاق السكن"
        :message="buildings.error"
        @retry="buildings.fetch"
      />
      <p v-else-if="!buildings.data?.length" class="feature-page__empty">لا توجد مبانٍ نشطة ضمن نطاقك.</p>
      <ul v-else class="today-portfolio__list">
        <li v-for="item in buildings.data" :key="item.building">
          <button type="button" :aria-pressed="building === item.building" @click="selectBuilding(item.building)">
            <span class="record-identity">
              <strong dir="auto">{{ item.building_title }}</strong>
              <bdi class="record-reference" dir="auto" translate="no">{{ item.building }}</bdi>
            </span>
            <span>{{ item.occupied }} مشغول · {{ item.available }} متاح · {{ item.blocked + item.oos }} غير جاهز</span>
            <small>نسبة الإشغال {{ item.occupancy_pct }}٪</small>
          </button>
        </li>
      </ul>
    </section>

    <p v-if="!building" class="feature-page__empty">اختر المبنى لعرض أعمال اليوم.</p>
    <LoadingIndicator v-else-if="loading && !grid.data" aria-label="جارٍ تحميل أعمال اليوم" />
    <template v-else>
      <ErrorMessage v-if="error" :message="error" />
      <div v-if="canSeeBeds || canSeeArrivals || canSeeMaintenance || canSeeSafety" class="today-metrics">
        <RouterLink v-if="canSeeBeds" to="/beds"><strong>{{ availableBeds }}</strong><span>سرير متاح</span><small>{{ occupiedBeds }} مشغول، {{ unavailableBeds }} غير جاهز</small></RouterLink>
        <RouterLink v-if="canSeeArrivals" to="/arrivals"><strong>{{ arrivals.data?.pending || 0 }}</strong><span>قادم بانتظار الاستقبال</span><small>{{ arrivals.data?.arrived || 0 }} تم تسجيله اليوم</small></RouterLink>
        <RouterLink v-if="canSeeMaintenance" to="/maintenance"><strong>{{ requests.data?.open_requests || 0 }}</strong><span>طلب مفتوح</span><small>صيانة وشكاوى السكان</small></RouterLink>
        <RouterLink v-if="canSeeSafety" to="/rounds"><strong>{{ dueRounds }}</strong><span>جولة سلامة مستحقة</span><small>{{ safety.data?.awaiting?.length || 0 }} بانتظار الاعتماد</small></RouterLink>
      </div>

      <section v-if="canSeeArrivals || canSeeBeds || canSeeCustody || canCreateMaintenance" class="today-actions" aria-labelledby="today-actions-title">
        <div><p class="feature-kicker">إجراءات سريعة</p><h3 id="today-actions-title">ابدأ من المهمة</h3></div>
        <nav class="today-action-list" aria-label="إجراءات اليوم">
          <RouterLink v-if="canSeeArrivals" to="/arrivals"><span>استقبال وتسكين</span><small>سجّل القادم واختر سريره</small></RouterLink>
          <RouterLink v-if="canSeeBeds" to="/beds"><span>الغرف والأسرّة</span><small>جاهزية الغرف والمغادرة</small></RouterLink>
          <RouterLink v-if="canSeeCustody" to="/custody"><span>العهد</span><small>تسليم العهد واستلامها</small></RouterLink>
          <RouterLink v-if="canCreateMaintenance" to="/maintenance/new"><span>طلب صيانة</span><small>سجّل بلاغاً للمبنى</small></RouterLink>
        </nav>
      </section>
    </template>
  </section>
</template>
