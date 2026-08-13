<script setup>
import { computed, ref, watch } from "vue";
import { ErrorMessage, LoadingIndicator, createResource } from "frappe-ui";
import BuildingPicker from "../components/BuildingPicker.vue";
import { building } from "../building.js";

const capabilities = globalThis.window?.apex_portal?.capabilities || [];
const canSeeSafety = capabilities.includes("safety_read");
const grid = createResource({ url: "apex.habitat.api.front_desk.get_building_grid" });
const requests = createResource({ url: "apex.habitat.api.front_desk.building_open_requests" });
const arrivals = createResource({ url: "apex.habitat.api.arrivals_desk.get_expected_arrivals" });
const safety = createResource({ url: "apex.habitat.api.safety_checklist.get_due_cadences" });
const error = ref("");
const loading = computed(() => [grid, requests, arrivals].some((resource) => resource.loading));
const summary = computed(() => grid.data?.summary || {});
const availableBeds = computed(() => Number(summary.value.available || 0));
const occupiedBeds = computed(() => Number(summary.value.occupied || 0));
const unavailableBeds = computed(() => ["blocked", "out_of_service"]
  .reduce((total, key) => total + Number(summary.value[key] || 0), 0));
const dueRounds = computed(() => safety.data?.due?.length || 0);

async function load() {
  error.value = "";
  if (!building.value) return;
  const jobs = [
    grid.fetch({ building: building.value }),
    requests.fetch({ building: building.value }),
    arrivals.fetch({ building: building.value }),
  ];
  if (canSeeSafety) jobs.push(safety.fetch({ building: building.value }));
  const results = await Promise.allSettled(jobs);
  if (results.some((result) => result.status === "rejected")) {
    error.value = "تعذّر تحديث جزء من لوحة اليوم. يمكنك متابعة بقية الأعمال الظاهرة.";
  }
}

watch(building, load, { immediate: true });
</script>
<template>
  <section class="feature-page today-page">
    <header class="feature-page__header arrivals-heading">
      <div><p class="feature-kicker">وردية السكن</p><h2>ما يحتاج انتباهك اليوم</h2><p>صورة سريعة للمبنى، ثم أقرب إجراء.</p></div>
      <BuildingPicker />
    </header>

    <p v-if="!building" class="feature-page__empty">اختر المبنى لعرض أعمال اليوم.</p>
    <LoadingIndicator v-else-if="loading && !grid.data" aria-label="جارٍ تحميل أعمال اليوم" />
    <template v-else>
      <ErrorMessage v-if="error" :message="error" />
      <div class="today-metrics">
        <RouterLink to="/beds"><strong>{{ availableBeds }}</strong><span>سرير متاح</span><small>{{ occupiedBeds }} مشغول، {{ unavailableBeds }} غير جاهز</small></RouterLink>
        <RouterLink to="/arrivals"><strong>{{ arrivals.data?.pending || 0 }}</strong><span>قادم بانتظار الاستقبال</span><small>{{ arrivals.data?.arrived || 0 }} تم تسجيله اليوم</small></RouterLink>
        <RouterLink to="/maintenance"><strong>{{ requests.data?.open_requests || 0 }}</strong><span>طلب مفتوح</span><small>صيانة وشكاوى السكان</small></RouterLink>
        <RouterLink v-if="canSeeSafety" to="/rounds"><strong>{{ dueRounds }}</strong><span>جولة سلامة مستحقة</span><small>{{ safety.data?.awaiting?.length || 0 }} بانتظار الاعتماد</small></RouterLink>
      </div>

      <section class="today-actions" aria-labelledby="today-actions-title">
        <div><p class="feature-kicker">إجراءات سريعة</p><h3 id="today-actions-title">ابدأ من المهمة</h3></div>
        <nav class="today-action-list" aria-label="إجراءات اليوم">
          <RouterLink to="/arrivals"><span>استقبال وتسكين</span><small>سجّل القادم واختر سريره</small></RouterLink>
          <RouterLink to="/beds"><span>الغرف والأسرّة</span><small>جاهزية الغرف والمغادرة</small></RouterLink>
          <RouterLink to="/custody"><span>العهد</span><small>تسليم العهد واستلامها</small></RouterLink>
          <RouterLink to="/maintenance/new"><span>طلب صيانة</span><small>سجّل بلاغاً للمبنى</small></RouterLink>
        </nav>
      </section>
    </template>
  </section>
</template>
