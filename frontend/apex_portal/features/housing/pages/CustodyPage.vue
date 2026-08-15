<script setup>
import { computed, reactive, ref, watch } from "vue";
import { Button, ErrorMessage, FormControl, createResource, toast } from "frappe-ui";
import BuildingPicker from "../components/BuildingPicker.vue";
import { building } from "../building.js";
import { nextCustodySelection } from "../custodyState.js";
import { safeErrorMessage } from "../../../core/errorMessage.js";

const state = reactive({ building: "", holder: null, cart: [] });
const mode = ref("issue");
const holderType = ref("Employee");
const holderId = ref("");
const scan = ref("");
const error = ref("");
const capabilities = globalThis.window?.apex_portal?.capabilities || [];
const canIssue = capabilities.includes("issue_custody");
const canReturn = capabilities.includes("return_custody");
const catalog = createResource({
  url: "apex.habitat.api.custody_kiosk.get_kiosk_catalog",
  makeParams: () => ({ building: state.building }),
});
const held = createResource({
  url: "apex.habitat.api.custody_kiosk.get_party_custody",
  makeParams: () => ({
    party_type: state.holder?.party_type || "",
    party: state.holder?.party || "",
  }),
});
const resolver = createResource({ url: "apex.habitat.api.custody_kiosk.resolve_scan" });
const issue = createResource({ url: "apex.habitat.api.custody_kiosk.issue_cart" });
const returnItems = createResource({ url: "apex.habitat.api.custody_kiosk.return_cart" });

const articles = computed(() => catalog.data?.articles || []);
const heldLines = computed(() => held.data?.lines || []);
const outOfStock = computed(() => articles.value
  .filter((article) => Number(article.store_balance) <= 0)
  .map((article) => article.article_name || article.article));
const allowed = computed(() => mode.value === "issue" ? canIssue : canReturn);
const actionLabel = computed(() => mode.value === "issue" ? "تسليم العهدة" : "استلام العهدة المرتجعة");

function replace(change) { Object.assign(state, nextCustodySelection(state, change)); }
async function refreshBalances() {
  const requests = [];
  if (state.building) requests.push(catalog.fetch());
  if (state.holder) requests.push(held.fetch());
  await Promise.all(requests);
}
// The picker's selection survives navigation, so the catalogue must load for a building
// that was already chosen on another screen — not only when the choice changes here.
watch(building, async (value) => {
  replace({ building: value });
  await refreshBalances();
}, { immediate: true });
watch(mode, () => replace({ holder: state.holder }));
async function selectHolder() {
  replace({ holder: { party_type: holderType.value, party: holderId.value } });
  await held.fetch();
}
function addArticle(article) {
  const current = state.cart.find((line) => line.article === article.article);
  if (current) current.qty += 1;
  // Carry the catalogue's own label so the cart reads as an item, not as a record id.
  else state.cart.push({ article: article.article, article_name: article.article_name, qty: 1 });
}
function addReturn(line) {
  const key = `${line.custody_issue}:${line.article}`;
  const current = state.cart.find((item) => item.key === key);
  if (current) current.qty = Math.min(current.qty + 1, line.qty);
  else state.cart.push({ key, custody_issue: line.custody_issue, article: line.article, article_name: line.article_name, qty: 1, condition_on_return: "Good" });
}
async function addScan() {
  error.value = "";
  try {
    const row = await resolver.fetch({ code: scan.value, party_type: holderType.value, building: state.building });
    if (row?.kind === "worker") {
      holderType.value = row.party_type;
      holderId.value = row.party;
      await selectHolder();
    } else if (row?.kind === "article" && mode.value === "issue") {
      addArticle(row.article);
    } else {
      throw new Error("لم نتعرف على الرمز في هذه العملية.");
    }
    scan.value = "";
  } catch (exception) { error.value = safeErrorMessage(exception, "تعذر قراءة الرمز."); }
}
async function submit() {
  error.value = "";
  try {
    const action = mode.value === "issue" ? issue : returnItems;
    const params = {
      party_type: state.holder.party_type,
      party: state.holder.party,
      items_json: JSON.stringify(state.cart.map(({ key, ...line }) => line)),
    };
    if (mode.value === "issue") params.building = state.building;
    await action.submit(params);
    toast.create({ type: "success", message: mode.value === "issue" ? "تم تسليم العهدة" : "تم استلام العهدة" });
    replace({ holder: state.holder });
    await refreshBalances();
  } catch (exception) { error.value = safeErrorMessage(exception, "تعذر تسليم العهدة."); }
}
</script>
<template>
  <section class="feature-page"><h2>عهد السكن</h2><BuildingPicker />
    <div class="feature-card feature-form">
      <div class="feature-actions" role="group" aria-label="نوع العملية">
        <Button :variant="mode === 'issue' ? 'solid' : 'subtle'" :aria-pressed="mode === 'issue'" @click="mode = 'issue'">تسليم</Button>
        <Button :variant="mode === 'return' ? 'solid' : 'subtle'" :aria-pressed="mode === 'return'" @click="mode = 'return'">استلام مرتجع</Button>
      </div>
      <FormControl v-model="holderType" type="select" label="نوع الحائز" :options="[{ label: 'موظف', value: 'Employee' }, { label: 'عامل مؤقت', value: 'Temporary Worker' }]" />
      <FormControl v-model="holderId" label="رقم الحائز" />
      <Button variant="subtle" :disabled="!holderId" @click="selectHolder">اختيار الحائز</Button>
      <FormControl v-model="scan" label="رمز الصنف" />
      <Button variant="subtle" :disabled="!state.holder || !scan" :loading="resolver.loading" @click="addScan">إضافة الصنف</Button>
      <div v-if="state.holder && mode === 'issue'" class="feature-page__list">
        <!-- A greyed article is out of stock in this building's store; the number alone
             inside the label does not say that is why it cannot be picked. -->
        <p v-if="outOfStock.length" class="feature-page__empty">أصناف بدون رصيد في مستودع المبنى، ولا يمكن تسليمها: {{ outOfStock.join("، ") }}.</p>
        <Button v-for="article in articles" :key="article.article" variant="subtle" :disabled="Number(article.store_balance) <= 0" @click="addArticle(article)">
          {{ article.article_name }} · {{ article.store_balance ?? '—' }}
        </Button>
      </div>
      <div v-else-if="state.holder" class="feature-page__list">
        <Button v-for="line in heldLines" :key="`${line.custody_issue}:${line.article}`" variant="subtle" @click="addReturn(line)">
          {{ line.article_name }} · {{ line.qty }}
        </Button>
      </div>
      <ul><li v-for="row in state.cart" :key="row.key || row.article" dir="auto">{{ row.article_name || row.article }} × {{ row.qty }}</li></ul>
      <p v-if="!allowed" class="feature-page__empty">يمكنك مشاهدة العهد، لكن صلاحية تنفيذ هذه العملية غير متاحة.</p>
      <ErrorMessage v-if="error" :message="error" />
      <Button theme="green" variant="solid" :disabled="!allowed || !state.holder || !state.cart.length" :loading="issue.loading || returnItems.loading" @click="submit">{{ actionLabel }}</Button>
    </div>
  </section>
</template>
