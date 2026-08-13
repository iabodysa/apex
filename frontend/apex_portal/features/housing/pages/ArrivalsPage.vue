<script setup>
import { computed, reactive, ref, watch } from "vue";
import { Badge, Button, ErrorMessage, FormControl, LoadingIndicator, createResource, toast } from "frappe-ui";
import { useRouter } from "vue-router";
import BuildingPicker from "../components/BuildingPicker.vue";
import { building } from "../building.js";
import {
  arrivalRegistrationParams,
  normalizeWorkerLinkResult,
} from "../arrivalFlow.js";

const router = useRouter();
const capabilities = globalThis.window?.apex_portal?.capabilities || [];
const canRegister = capabilities.includes("register_worker");
const arrivals = createResource({
  url: "apex.habitat.api.arrivals_desk.get_expected_arrivals",
  makeParams: () => ({ building: building.value }),
});
const search = createResource({ url: "apex.habitat.api.arrivals_desk.search_arrivals_workers" });
const register = createResource({ url: "apex.habitat.api.arrivals_desk.register_temporary_worker" });
const slip = createResource({ url: "apex.habitat.api.arrivals_desk.get_arrival_slip" });
const links = createResource({
  url: "apex.apex_core.doctype.masar_worker_token.masar_worker_token.batch_issue_worker_links",
});
const workers = computed(() => arrivals.data?.workers || []);
const query = ref("");
const candidates = ref([]);
const selectedManifest = ref(null);
const registered = ref(null);
const issuedLink = ref(null);
const error = ref("");
const form = reactive({ worker_name: "", passport_number: "", nationality: "", cell_number: "" });

function load() {
  if (building.value) arrivals.fetch();
}

function candidateFrom(row) {
  return {
    party_type: row.party_type || "Temporary Worker",
    party: row.party || row.temporary_worker,
    label: row.label || row.worker_name || row.party || row.temporary_worker,
    project: row.project || "",
  };
}

function chooseBed(row) {
  const candidate = candidateFrom(row);
  if (!candidate.party) return;
  router.push({ path: "/beds", query: candidate });
}

function prepareManifest(row) {
  selectedManifest.value = row;
  form.worker_name = row.worker_name || "";
  form.passport_number = row.passport_number || "";
  form.nationality = row.nationality || "";
}

async function findWorker() {
  error.value = "";
  try {
    candidates.value = await search.fetch({ building: building.value, txt: query.value });
  } catch (reason) {
    error.value = reason?.message || "تعذّر البحث عن العامل.";
  }
}

async function addTemporary() {
  error.value = "";
  try {
    const result = await register.submit(
      arrivalRegistrationParams(form, selectedManifest.value, building.value),
    );
    registered.value = { ...result, project: selectedManifest.value?.project || "" };
    selectedManifest.value = null;
    Object.assign(form, { worker_name: "", passport_number: "", nationality: "", cell_number: "" });
    toast({ title: "تم تسجيل العامل", icon: "check" });
    await arrivals.fetch();
  } catch (reason) {
    error.value = reason?.message || "تعذّر تسجيل العامل.";
  }
}

async function issueLink(row) {
  error.value = "";
  try {
    const result = await links.submit({ employees_json: JSON.stringify([row.party]) });
    issuedLink.value = normalizeWorkerLinkResult(result);
    if (!issuedLink.value) throw new Error("لم يصدر رابط للعامل.");
  } catch (reason) {
    error.value = reason?.message || "تعذّر إصدار رابط العامل.";
  }
}

async function printSlip(row) {
  error.value = "";
  const popup = globalThis.open?.("", "_blank", "noopener,noreferrer");
  try {
    const result = await slip.submit({
      party_type: row.party_type || "Temporary Worker",
      party: row.party || row.temporary_worker,
    });
    if (!popup) throw new Error("اسمح بفتح نافذة الطباعة ثم حاول مرة أخرى.");
    const url = URL.createObjectURL(new Blob([result.html], { type: "text/html;charset=utf-8" }));
    popup.location.replace(url);
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (reason) {
    popup?.close();
    error.value = reason?.message || "تعذّر تجهيز بطاقة الوصول.";
  }
}

watch(building, load, { immediate: true });
</script>

<template>
  <section class="feature-page arrivals-page">
    <header class="feature-page__header arrivals-heading">
      <div><p class="feature-kicker">مكتب الوصول</p><h2>استقبال العامل حتى سريره</h2><p>سجّل القادم، اختر له سريراً، ثم أكمل العهد.</p></div>
      <BuildingPicker />
    </header>

    <div v-if="!building" class="feature-page__empty">اختر المبنى لعرض قائمة الوصول.</div>
    <LoadingIndicator v-else-if="arrivals.loading && !workers.length" aria-label="جارٍ تحميل القادمين" />
    <ErrorMessage v-else-if="arrivals.error" message="تعذّر تحميل قائمة الوصول." />

    <template v-else-if="building">
      <div class="arrival-metrics">
        <article><strong>{{ arrivals.data?.total || 0 }}</strong><span>متوقع اليوم</span></article>
        <article><strong>{{ arrivals.data?.arrived || 0 }}</strong><span>تم تسجيله</span></article>
        <article><strong>{{ arrivals.data?.pending || 0 }}</strong><span>بانتظار الإجراء</span></article>
      </div>
      <ErrorMessage v-if="error" :message="error" />

      <article v-if="registered" class="arrival-focus">
        <div><span>جاهز للتسكين</span><h3>{{ registered.label }}</h3><p>اكتمل تسجيل الهوية. اختر السرير المناسب الآن.</p></div>
        <Button theme="green" variant="solid" @click="chooseBed(registered)">اختيار سرير</Button>
      </article>

      <article v-if="issuedLink" class="arrival-link-card">
        <div><span>رابط العامل</span><h3>جاهز للإرسال</h3><a :href="issuedLink.link" target="_blank" rel="noopener noreferrer">فتح الرابط</a></div>
        <img v-if="issuedLink.qr" :src="issuedLink.qr" alt="رمز دخول العامل" />
      </article>

      <section class="arrival-panel">
        <div class="arrival-panel__title"><h3>ابحث عن عامل مسجل</h3><span>بالاسم أو الرقم</span></div>
        <div class="arrival-search"><FormControl v-model="query" label="العامل" /><Button icon="search" variant="outline" :loading="search.loading" @click="findWorker">بحث</Button></div>
        <article v-for="row in candidates" :key="`${row.party_type}:${row.party}`" class="arrival-row">
          <div><strong>{{ row.label }}</strong><small>{{ row.sub }}</small></div>
          <Badge :label="row.party_type === 'Employee' ? 'موظف' : 'عامل مؤقت'" />
          <div class="feature-actions">
            <Button v-if="row.party_type === 'Employee'" variant="subtle" @click="issueLink(row)">رابط العامل</Button>
            <Button theme="green" variant="solid" @click="chooseBed(row)">اختيار سرير</Button>
          </div>
        </article>
      </section>

      <section class="arrival-panel">
        <div class="arrival-panel__title"><h3>قائمة اليوم</h3><span>{{ workers.length }} عامل</span></div>
        <p v-if="!workers.length" class="feature-page__empty">لا توجد دفعة وصول لهذا المبنى اليوم.</p>
        <article v-for="row in workers" :key="row.row" class="arrival-row">
          <div><strong>{{ row.worker_name }}</strong><small>{{ row.passport_number || 'لا يوجد رقم جواز' }}، {{ row.labour_supplier || row.project || 'بدون جهة محددة' }}</small></div>
          <Badge :theme="row.arrived ? 'green' : 'orange'" :label="row.arrived ? 'مسجل' : 'منتظر'" />
          <div class="feature-actions">
            <Button v-if="row.arrived" variant="subtle" @click="printSlip(row)">بطاقة الوصول</Button>
            <Button v-if="row.arrived" theme="green" variant="solid" @click="chooseBed(row)">اختيار سرير</Button>
            <Button v-else-if="canRegister" theme="green" variant="solid" @click="prepareManifest(row)">تسجيل الوصول</Button>
          </div>
        </article>
      </section>

      <form v-if="canRegister" class="arrival-panel arrival-form" @submit.prevent="addTemporary">
        <div class="arrival-panel__title"><h3>{{ selectedManifest ? `تسجيل ${selectedManifest.worker_name}` : 'إضافة عامل غير موجود في القائمة' }}</h3><Button v-if="selectedManifest" type="button" variant="ghost" @click="selectedManifest = null">إلغاء</Button></div>
        <div class="arrival-form__grid">
          <FormControl v-model="form.worker_name" label="اسم العامل" required />
          <FormControl v-model="form.passport_number" label="رقم الجواز" required />
          <FormControl v-model="form.nationality" label="الجنسية" />
          <FormControl v-model="form.cell_number" label="رقم الجوال" />
        </div>
        <Button type="submit" theme="green" variant="solid" :loading="register.loading" :disabled="!form.worker_name || !form.passport_number">تسجيل العامل</Button>
      </form>
    </template>
  </section>
</template>
