<script setup>
import { computed, inject, onBeforeUnmount, ref, watch } from "vue";
import { Badge, Button, ErrorMessage, Progress, createResource, toast } from "frappe-ui";
import PortalErrorState from "../../../components/PortalErrorState.vue";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import { useRouter } from "vue-router";
import BuildingPicker from "../components/BuildingPicker.vue";
import ArrivalWorkerSearch from "../components/ArrivalWorkerSearch.vue";
import ArrivalRegistrationForm from "../components/ArrivalRegistrationForm.vue";
import { building } from "../building.js";
import { safeErrorMessage } from "../../../core/errorMessage.js";
import { normalizeWorkerLinkResult, summarizeArrivalSession } from "../arrivalFlow.js";
import { __ } from "../../../core/i18n.js";

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

const subscribeBuilding = inject("portalBuildingSubscribe", () => () => {});
let unsubscribers = [];
let liveBuilding = null;

function stopLive() {
  liveBuilding = null;
  while (unsubscribers.length) unsubscribers.pop()();
}

function startLive(name) {
  if (name === liveBuilding) return;
  liveBuilding = name;
  while (unsubscribers.length) unsubscribers.pop()();
  if (name) unsubscribers.push(subscribeBuilding(name, "doc_update", () => arrivals.fetch()) || (() => {}));
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
  toast.create({ type: "success", message: __("The worker was registered") });
  await arrivals.fetch();
}

async function issueLink(row) {
  error.value = "";
  try {
    const result = await links.submit({ employees_json: JSON.stringify([row.party]) });
    issuedLink.value = normalizeWorkerLinkResult(result);
    if (!issuedLink.value) throw new Error(__("No link was issued for the worker."));
  } catch (reason) {
    error.value = safeErrorMessage(reason, __("Could not issue the worker's link."));
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
    if (!popup) throw new Error(__("Allow the print window to open then try again."));
    const url = URL.createObjectURL(new Blob([result.html], { type: "text/html;charset=utf-8" }));
    popup.location.replace(url);
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (reason) {
    popup?.close();
    error.value = safeErrorMessage(reason, __("Could not prepare the arrival card."));
  }
}

watch(building, load, { immediate: true });
watch(building, startLive, { immediate: true });
onBeforeUnmount(stopLive);
</script>

<template>
  <section class="feature-page arrivals-page">
    <header class="feature-page__header arrivals-heading">
      <div><p class="feature-kicker">{{ __("Arrival Desk") }}</p><h2>{{ __("Receive the worker through to their bed") }}</h2><p>{{ __("Register the arrival, choose their bed, then complete the custody handover.") }}</p></div>
      <BuildingPicker />
    </header>

    <div v-if="!building" class="feature-page__empty">{{ __("Select the building to view the arrivals list.") }}</div>
    <PortalSkeleton v-else-if="arrivals.loading && !workers.length" :rows="3" :label="__('Loading Arrivals')" />
    <PortalErrorState v-else-if="arrivals.error" :title="__('Could not load the arrivals list')" :message="arrivals.error" @retry="load" />

    <template v-else-if="building">
      <div class="arrival-metrics">
        <article><strong>{{ arrivals.data?.total || 0 }}</strong><span>{{ __("Expected Today") }}</span></article>
        <article><strong>{{ session.registered }}</strong><span>{{ __("registered") }}</span></article>
        <article><strong>{{ session.housed }}</strong><span>{{ __("housed") }}</span></article>
      </div>
      <section v-if="session.total" class="arrival-session" aria-labelledby="arrival-session-title">
        <div class="arrival-session__copy">
          <span>{{ __("Arrival Session") }}</span>
          <h3 id="arrival-session-title">{{ session.next ? __("Next: {0}", [session.next.worker_name]) : __("Today's batch is complete") }}</h3>
          <p>{{ __("{0} of {1} have reached their beds.", [session.housed, session.total]) }}</p>
        </div>
        <Progress :value="session.progress" :label="`${session.progress}٪`" size="lg" />
        <Button v-if="session.next" theme="green" variant="solid" @click="continueSession">
          {{ session.nextAction === 'assign-bed' ? __("Choose a Bed") : __("Register Arrival") }}
        </Button>
      </section>
      <ErrorMessage v-if="error" :message="error" />

      <article v-if="registered" class="arrival-focus">
        <div><span>{{ __("Ready for Check-in") }}</span><h3>{{ registered.label }}</h3><p>{{ __("Identity registration is complete. Choose the right bed now.") }}</p></div>
        <Button theme="green" variant="solid" @click="chooseBed(registered)">{{ __("Choose a Bed") }}</Button>
      </article>

      <article v-if="issuedLink" class="arrival-link-card">
        <div><span>{{ __("Link the Worker") }}</span><h3>{{ __("Ready to Send") }}</h3><a :href="issuedLink.link" target="_blank" rel="noopener noreferrer">{{ __("Open the Link") }}</a></div>
        <img v-if="issuedLink.qr" :src="issuedLink.qr" :alt="__('Worker entry code')" />
      </article>

      <ArrivalWorkerSearch
        :building="building"
        @choose-bed="chooseBed"
        @issue-link="issueLink"
        @error="error = $event"
      />

      <section class="arrival-panel">
        <div class="arrival-panel__title"><h3>{{ __("Today's List") }}</h3><span>{{ workers.length }} {{ __("Worker") }}</span></div>
        <p v-if="!workers.length" class="feature-page__empty">{{ __("No arrival batch for this building today.") }}</p>
        <article v-for="row in workers" :key="row.row" class="arrival-row">
          <div><strong dir="auto">{{ row.worker_name }}</strong><small><bdi dir="auto" translate="no">{{ row.passport_number || __("No passport number") }}</bdi>، <bdi dir="auto">{{ row.labour_supplier || row.project || __("No specific party") }}</bdi></small></div>
          <Badge :theme="row.housed ? 'green' : row.arrived ? 'blue' : 'orange'" :label="row.housed ? __('housed') : row.arrived ? __('Registered') : __('Waiting')" />
          <div class="feature-actions">
            <Button v-if="row.arrived" variant="subtle" @click="printSlip(row)">{{ __("Arrival Card") }}</Button>
            <Button v-if="row.arrived && !row.housed" theme="green" variant="solid" @click="chooseBed(row)">{{ __("Choose a Bed") }}</Button>
            <!-- Only a worker who has not been registered yet can be registered; a housed
                 row is finished and carries its own badge instead of an action. -->
            <Button v-else-if="canRegister && !row.arrived" theme="green" variant="solid" @click="prepareManifest(row)">{{ __("Register Arrival") }}</Button>
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
