<script setup>
import { computed, ref, watch } from "vue";
import { Badge, Button, ErrorMessage, Progress, createResource, toast } from "frappe-ui";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import { useRouter } from "vue-router";
import BuildingPicker from "../components/BuildingPicker.vue";
import ArrivalWorkerSearch from "../components/ArrivalWorkerSearch.vue";
import ArrivalRegistrationForm from "../components/ArrivalRegistrationForm.vue";
import { building } from "../building.js";
import { safeErrorMessage } from "../../../core/errorMessage.js";
import { normalizeWorkerLinkResult, summarizeArrivalSession } from "../arrivalFlow.js";

const router = useRouter();
const capabilities = globalThis.window?.apex_portal?.capabilities || [];
const canRegister = capabilities.includes("register_worker");
const arrivals = createResource({
  url: "apex.habitat.api.arrivals_desk.get_expected_arrivals",
  makeParams: () => ({ building: building.value }),
});
const slip = createResource({ url: "apex.habitat.api.arrivals_desk.get_arrival_slip" });
const links = createResource({
  url: "apex.apex_core.doctype.masar_worker_token.masar_worker_token.batch_issue_worker_links",
});
const workers = computed(() => arrivals.data?.workers || []);
const session = computed(() => summarizeArrivalSession(workers.value));
const selectedManifest = ref(null);
const registered = ref(null);
const issuedLink = ref(null);
const error = ref("");

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

// A fresh object on every pick, so choosing the same row twice seeds the form again.
function prepareManifest(row) {
  selectedManifest.value = { ...row };
}

function continueSession() {
  const row = session.value.next;
  if (!row) return;
  if (session.value.nextAction === "assign-bed") chooseBed(row);
  else prepareManifest(row);
}

async function onRegistered(result) {
  registered.value = { ...result, project: selectedManifest.value?.project || "" };
  selectedManifest.value = null;
  toast.create({ type: "success", message: "تم تسجيل العامل" });
  await arrivals.fetch();
}

async function issueLink(row) {
  error.value = "";
  try {
    const result = await links.submit({ employees_json: JSON.stringify([row.party]) });
    issuedLink.value = normalizeWorkerLinkResult(result);
    if (!issuedLink.value) throw new Error("لم يصدر رابط للعامل.");
  } catch (reason) {
    error.value = safeErrorMessage(reason, "تعذّر إصدار رابط العامل.");
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
    error.value = safeErrorMessage(reason, "تعذّر تجهيز بطاقة الوصول.");
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
    <PortalSkeleton v-else-if="arrivals.loading && !workers.length" :rows="3" label="جارٍ تحميل القادمين" />
    <ErrorMessage v-else-if="arrivals.error" message="تعذّر تحميل قائمة الوصول." />

    <template v-else-if="building">
      <div class="arrival-metrics">
        <article><strong>{{ arrivals.data?.total || 0 }}</strong><span>متوقع اليوم</span></article>
        <article><strong>{{ session.registered }}</strong><span>تم تسجيله</span></article>
        <article><strong>{{ session.housed }}</strong><span>تم تسكينه</span></article>
      </div>
      <section v-if="session.total" class="arrival-session" aria-labelledby="arrival-session-title">
        <div class="arrival-session__copy">
          <span>جلسة الوصول</span>
          <h3 id="arrival-session-title">{{ session.next ? `التالي: ${session.next.worker_name}` : "اكتملت دفعة اليوم" }}</h3>
          <p>{{ session.housed }} من {{ session.total }} وصلوا إلى أسرّتهم.</p>
        </div>
        <Progress :value="session.progress" :label="`${session.progress}٪`" size="lg" />
        <Button v-if="session.next" theme="green" variant="solid" @click="continueSession">
          {{ session.nextAction === 'assign-bed' ? 'اختيار سرير' : 'تسجيل الوصول' }}
        </Button>
      </section>
      <ErrorMessage v-if="error" :message="error" />

      <article v-if="registered" class="arrival-focus">
        <div><span>جاهز للتسكين</span><h3>{{ registered.label }}</h3><p>اكتمل تسجيل الهوية. اختر السرير المناسب الآن.</p></div>
        <Button theme="green" variant="solid" @click="chooseBed(registered)">اختيار سرير</Button>
      </article>

      <article v-if="issuedLink" class="arrival-link-card">
        <div><span>رابط العامل</span><h3>جاهز للإرسال</h3><a :href="issuedLink.link" target="_blank" rel="noopener noreferrer">فتح الرابط</a></div>
        <img v-if="issuedLink.qr" :src="issuedLink.qr" alt="رمز دخول العامل" />
      </article>

      <ArrivalWorkerSearch
        :building="building"
        @choose-bed="chooseBed"
        @issue-link="issueLink"
        @error="error = $event"
      />

      <section class="arrival-panel">
        <div class="arrival-panel__title"><h3>قائمة اليوم</h3><span>{{ workers.length }} عامل</span></div>
        <p v-if="!workers.length" class="feature-page__empty">لا توجد دفعة وصول لهذا المبنى اليوم.</p>
        <article v-for="row in workers" :key="row.row" class="arrival-row">
          <div><strong>{{ row.worker_name }}</strong><small>{{ row.passport_number || 'لا يوجد رقم جواز' }}، {{ row.labour_supplier || row.project || 'بدون جهة محددة' }}</small></div>
          <Badge :theme="row.housed ? 'green' : row.arrived ? 'blue' : 'orange'" :label="row.housed ? 'تم تسكينه' : row.arrived ? 'مسجل' : 'منتظر'" />
          <div class="feature-actions">
            <Button v-if="row.arrived" variant="subtle" @click="printSlip(row)">بطاقة الوصول</Button>
            <Button v-if="row.arrived && !row.housed" theme="green" variant="solid" @click="chooseBed(row)">اختيار سرير</Button>
            <!-- Only a worker who has not been registered yet can be registered; a housed
                 row is finished and carries its own badge instead of an action. -->
            <Button v-else-if="canRegister && !row.arrived" theme="green" variant="solid" @click="prepareManifest(row)">تسجيل الوصول</Button>
          </div>
        </article>
      </section>

      <ArrivalRegistrationForm
        v-if="canRegister"
        :manifest="selectedManifest"
        :building="building"
        @cancel="selectedManifest = null"
        @registered="onRegistered"
        @error="error = $event"
      />
    </template>
  </section>
</template>
