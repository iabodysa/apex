<script setup>
import { computed, reactive, ref, watch } from "vue";
import { Button, ErrorMessage, FormControl, createResource, toast } from "frappe-ui";
import BuildingPicker from "../components/BuildingPicker.vue";
import { building } from "../building.js";
import { nextCustodySelection } from "../custodyState.js";
import { safeErrorMessage } from "../../../core/errorMessage.js";
import { __ } from "../../../core/i18n.js";

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
const actionLabel = computed(() => mode.value === "issue" ? __("Custody Handover") : __("Return of Custody Items"));
// The kiosk greys three buttons in sequence — pick a holder, scan an article, submit — and the
// permission notice below covers only the last of them. These name the step still missing.
const holderReason = computed(() => (holderId.value ? "" : __("Type the holder number to enable selecting them.")));
const scanReason = computed(() => {
  if (!state.holder) return __("Select the holder before adding items.");
  if (!scan.value) return __("Scan the item code or type it to add it.");
  return "";
});
const submitReason = computed(() => {
  if (!allowed.value) return "";
  if (!state.holder) return __("Select the holder to complete the operation.");
  if (!state.cart.length) return __("Add at least one item to complete the operation.");
  return "";
});

function replace(change) { Object.assign(state, nextCustodySelection(state, change)); }
async function refreshBalances() {
  try {
    const requests = [];
    if (state.building) requests.push(catalog.fetch());
    if (state.holder) requests.push(held.fetch());
    await Promise.all(requests);
  } catch (exception) {
    error.value = safeErrorMessage(exception, __("Could not load the building's items."));
  }
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
      throw new Error(__("The code was not recognized for this operation."));
    }
    scan.value = "";
  } catch (exception) { error.value = safeErrorMessage(exception, __("Could not read the code.")); }
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
    toast.create({ type: "success", message: mode.value === "issue" ? __("The custody items were handed over") : __("The custody items were received") });
    replace({ holder: state.holder });
    await refreshBalances();
  } catch (exception) { error.value = safeErrorMessage(exception, __("Could not hand over the custody items.")); }
}
</script>
<template>
  <section class="feature-page"><h2>{{ __("Housing Custody") }}</h2><BuildingPicker />
    <div class="feature-card feature-form">
      <div class="feature-actions" role="group" :aria-label="__('Operation Type')">
        <Button :variant="mode === 'issue' ? 'solid' : 'subtle'" :aria-pressed="mode === 'issue'" @click="mode = 'issue'">{{ __("delivery") }}</Button>
        <Button :variant="mode === 'return' ? 'solid' : 'subtle'" :aria-pressed="mode === 'return'" @click="mode = 'return'">{{ __("Return Item") }}</Button>
      </div>
      <FormControl v-model="holderType" type="select" :label="__('Custody Holder Type')" :options="[{ label: __('Emp'), value: 'Employee' }, { label: __('Temporary Worker'), value: 'Temporary Worker' }]" />
      <FormControl v-model="holderId" :label="__('Holder Number')" />
      <p v-if="holderReason" class="feature-reason">{{ holderReason }}</p>
      <Button variant="subtle" :disabled="!holderId" @click="selectHolder">{{ __("Select Holder") }}</Button>
      <FormControl v-model="scan" :label="__('Item Code')" />
      <p v-if="scanReason" class="feature-reason">{{ scanReason }}</p>
      <Button variant="subtle" :disabled="!state.holder || !scan" :loading="resolver.loading" @click="addScan">{{ __("Add Item") }}</Button>
      <div v-if="state.holder && mode === 'issue'" class="feature-page__list">
        <p v-if="catalog.loading" class="feature-reason">{{ __("Loading the building's items…") }}</p>
        <template v-else>
          <!-- A greyed article is out of stock in this building's store; the number alone
               inside the label does not say that is why it cannot be picked. -->
          <p v-if="outOfStock.length" class="feature-page__empty">{{ __("Items with no balance in the building store cannot be handed over: {0}.", [outOfStock.join("، ")]) }}</p>
          <Button v-for="article in articles" :key="article.article" variant="subtle" :disabled="Number(article.store_balance) <= 0" @click="addArticle(article)">
            {{ article.article_name }} · {{ article.store_balance ?? '—' }}
          </Button>
        </template>
      </div>
      <div v-else-if="state.holder" class="feature-page__list">
        <p v-if="held.loading" class="feature-reason">{{ __("Loading held items…") }}</p>
        <template v-else>
          <Button v-for="line in heldLines" :key="`${line.custody_issue}:${line.article}`" variant="subtle" @click="addReturn(line)">
            {{ line.article_name }} · {{ line.qty }}
          </Button>
        </template>
      </div>
      <ul><li v-for="row in state.cart" :key="row.key || row.article" dir="auto">{{ row.article_name || row.article }} × {{ row.qty }}</li></ul>
      <p v-if="!allowed" class="feature-page__empty">{{ __("You can view the custody items, but you do not have permission to perform this operation.") }}</p>
      <ErrorMessage v-if="error" :message="error" />
      <p v-if="submitReason" class="feature-reason">{{ submitReason }}</p>
      <Button theme="green" variant="solid" :disabled="!allowed || !state.holder || !state.cart.length" :loading="issue.loading || returnItems.loading" @click="submit">{{ actionLabel }}</Button>
    </div>
  </section>
</template>
