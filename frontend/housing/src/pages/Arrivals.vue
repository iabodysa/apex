<!-- Copyright (c) 2026, afmcoltd -->
<template>
    <PageShell
        :state="expectedState"
        :title="t('arrivals.expected')"
        :loading-label="t('common.loading')"
        :skeleton-rows="4"
        :error-title="t('errors.arrivalsFailed')"
        :error-detail="expectedErrorMessage"
        :empty-title="t('arrivals.expectedEmpty')"
        @retry="expectedRes.reload()"
    >
        <template #actions>
            <Badge
                theme="green"
                size="lg"
                :label="t('arrivals.arrived', { arrived: manifest.arrived, total: manifest.total })"
            />
            <Button
                variant="ghost"
                size="md"
                :label="t('common.refresh')"
                @click="expectedRes.reload()"
            >
                <template #icon><Icon name="refresh" :size="18" /></template>
            </Button>
        </template>

        <template #empty-icon><Icon name="calendar" :size="24" /></template>

        <ul class="stack-tight">
            <li v-for="row in manifest.workers" :key="row.row" class="row-card">
                <div class="row-body">
                    <b>{{ row.worker_name }}</b>
                    <small
                        >{{ row.passport_number }} · {{ row.nationality || t("common.none") }}</small
                    >
                </div>
                <StatusLabel
                    v-if="row.arrived"
                    tone="success"
                    :label="t('arrivals.registered')"
                />
                <Button
                    v-else
                    size="lg"
                    variant="subtle"
                    :disabled="!canRegister"
                    :label="t('arrivals.registerCta')"
                    @click="openRegister(row)"
                />
            </li>
        </ul>
        <p v-if="!canRegister" class="hint">
            {{ t("access.needRegister") }}
        </p>
    </PageShell>

    <PageShell
        :state="searchState"
        :title="t('arrivals.searchWorker')"
        :loading-label="t('common.loading')"
        :skeleton-rows="3"
        :error-title="t('errors.searchFailed')"
        :error-detail="searchErrorMessage"
        :empty-title="t('arrivals.searchEmpty')"
        @retry="searchRes.reload()"
    >
        <template #actions>
            <Button
                size="lg"
                variant="outline"
                :disabled="!canRegister"
                :label="t('arrivals.registerTitle')"
                @click="openRegister(null)"
            >
                <template #prefix><Icon name="plus" :size="18" /></template>
            </Button>
        </template>

        <template #toolbar>
            <p v-if="!canRegister" class="hint">{{ t("access.needRegister") }}</p>
            <FormControl type="text" size="lg" :label="t('common.search')" v-model="query" />
        </template>

        <template #empty-icon><Icon name="search" :size="24" /></template>

        <ul v-if="workers.length" class="stack-tight">
            <li v-for="w in workers" :key="w.party_type + w.party" class="row-card">
                <div class="row-body">
                    <b>{{ w.label || w.party }}</b>
                    <small>{{ tEnum("custody", w.party_type) }}</small>
                </div>
                <Button
                    size="lg"
                    variant="subtle"
                    :label="t('arrivals.houseCta')"
                    @click="houseWorker(w)"
                />
                <Button
                    v-if="canIssueCustody"
                    size="lg"
                    variant="subtle"
                    :label="t('arrivals.custodyCta')"
                    @click="issueCustody(w)"
                />
                <Button
                    size="lg"
                    variant="ghost"
                    :label="t('arrivals.slipCta')"
                    :loading="busy === 'slip'"
                    @click="showSlip(w)"
                />
                <Button
                    v-if="w.party_type === 'Employee'"
                    size="lg"
                    variant="ghost"
                    :label="t('arrivals.linkCta')"
                    :loading="busy === 'link'"
                    @click="issueLink(w)"
                />
            </li>
        </ul>
    </PageShell>

    <Dialog v-model="registerOpen" :options="{ title: t('arrivals.registerTitle'), size: 'lg' }">
        <template #body-content>
            <div class="stack">
                <FormControl
                    type="text"
                    size="lg"
                    :label="t('arrivals.workerName')"
                    v-model="form.worker_name"
                />
                <FormControl
                    type="text"
                    size="lg"
                    :label="t('arrivals.passport')"
                    v-model="form.passport_number"
                />
                <div class="field-block">
                    <label class="field-label" for="arrivals-nationality">
                        {{ t("arrivals.nationality") }}
                    </label>
                    <Autocomplete
                        id="arrivals-nationality"
                        v-model="form.nationality"
                        :options="countryOptions"
                        :placeholder="t('arrivals.nationalitySearch')"
                    />
                    <p v-if="countriesRes.error" class="field-hint">{{ t("errors.listFailed") }}</p>
                </div>
                <FormControl
                    type="text"
                    size="lg"
                    :label="t('arrivals.phone')"
                    v-model="form.cell_number"
                />
                <FormControl
                    type="text"
                    size="lg"
                    :label="t('arrivals.iqama')"
                    v-model="form.iqama_number"
                />
                <ErrorMessage v-if="formError" :message="formError" />
            </div>
        </template>
        <template #actions>
            <Button
                class="dock-btn"
                size="2xl"
                variant="solid"
                theme="green"
                :disabled="!form.worker_name || !form.passport_number"
                :loading="busy === 'register'"
                :loading-text="t('arrivals.registering')"
                :label="t('arrivals.registerCta')"
                @click="doRegister"
            />
        </template>
    </Dialog>

    <Dialog v-model="linkOpen" :options="{ title: t('arrivals.linkCta'), size: 'sm' }">
        <template #body-content>
            <div class="stack">
                <img v-if="linkQr" class="link-qr" :src="linkQr" alt="" />
                <p v-if="linkUrl" class="hint break">{{ linkUrl }}</p>
                <ErrorMessage v-if="linkError" :message="linkError" />
            </div>
        </template>
        <template #actions>
            <Button
                size="2xl"
                variant="solid"
                :label="t('common.close')"
                @click="linkOpen = false"
            />
        </template>
    </Dialog>

    <Dialog v-model="slipOpen" :options="{ title: t('arrivals.slipTitle'), size: 'xl' }">
        <template #body-content>
            <ArrivalCard v-if="slipCard" :card="slipCard" />
            <ErrorMessage v-if="slipError" :message="slipError" />
        </template>
        <template #actions>
            <div class="sheet-actions">
                <Button
                    size="2xl"
                    variant="solid"
                    :label="t('arrivals.slipPrint')"
                    @click="printSlip"
                />
                <Button
                    size="xl"
                    variant="outline"
                    :label="t('common.close')"
                    @click="slipOpen = false"
                />
            </div>
        </template>
    </Dialog>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
    Autocomplete,
    Badge,
    Button,
    Dialog,
    ErrorMessage,
    FormControl,
    createListResource,
    createResource,
    toast,
} from "frappe-ui";
import ArrivalCard from "../components/ArrivalCard.vue";
import Icon from "../components/Icon.vue";
import PageShell from "../components/PageShell.vue";
import StatusLabel from "@shared/components/StatusLabel.vue";
import { call } from "@shared/call";
import { useI18n, apiErrorMessage, resourceErrorMessage } from "../i18n";
import { can, hasSection } from "../portal.js";
import { building, localDate } from "../session";

const { t, tEnum } = useI18n();
const router = useRouter();

const API = "apex.habitat.api.arrivals_desk.";
const canRegister = can("register_worker");
const canIssueCustody = can("issue_custody") && hasSection("custody");

const query = ref("");
const registerOpen = ref(false);
const formError = ref("");
const busy = ref("");
const linkOpen = ref(false);
const linkQr = ref("");
const linkUrl = ref("");
const linkError = ref("");
const slipOpen = ref(false);
const slipHtml = ref("");
const slipCard = ref(null);
const slipError = ref("");

const form = reactive({
    worker_name: "",
    passport_number: "",
    nationality: "",
    cell_number: "",
    iqama_number: "",
    batch_row: null,
    labour_supplier: null,
    project: null,
});

const expectedRes = createResource({
    url: API + "get_expected_arrivals",
    makeParams: () => ({ date: localDate(), building: building.value }),
});

const searchRes = createResource({
    url: API + "search_arrivals_workers",
    makeParams: () => ({ building: building.value, txt: query.value.trim() }),
});

const countriesRes = createListResource({
    doctype: "Country",
    fields: ["name"],
    orderBy: "name asc",
    pageLength: 300,
    auto: true,
});

const countryOptions = computed(() => [
    { label: t("common.none"), value: "" },
    ...(countriesRes.data || []).map((row) => ({ label: row.name, value: row.name })),
]);

const manifest = computed(() => {
    const data = expectedRes.data || {};
    return {
        workers: data.workers || [],
        total: data.total || 0,
        arrived: data.arrived || 0,
    };
});

const expectedErrorMessage = computed(() =>
    resourceErrorMessage(expectedRes.error, "errors.arrivalsFailed"),
);

const resultsQuery = ref("");
const workers = computed(() => {
    const term = query.value.trim();
    if (!term || resultsQuery.value !== term) return [];
    return searchRes.data || [];
});

const expectedState = computed(() => {
    if (expectedRes.loading && !manifest.value.total) return "loading";
    if (expectedRes.error) return "error";
    if (!manifest.value.workers.length) return "empty";
    return "ready";
});

const searchErrorMessage = computed(() =>
    resourceErrorMessage(searchRes.error, "errors.searchFailed"),
);
const searchState = computed(() => {
    if (workers.value.length) return "ready";
    if (searchRes.error) return "error";
    if (searchRes.loading && query.value.trim()) return "loading";
    if (!query.value.trim()) return "ready";
    return resultsQuery.value === query.value.trim() ? "empty" : "loading";
});

function fetchAll() {
    if (building.value) expectedRes.fetch();
}

watch(building, fetchAll);
onMounted(fetchAll);

let searchTimer = 0;
watch(query, () => {
    window.clearTimeout(searchTimer);
    if (!query.value.trim()) return;
    searchTimer = window.setTimeout(() => {
        const term = query.value.trim();
        searchRes.fetch().then(() => {
            resultsQuery.value = term;
        });
    }, 250);
});

function linkValue(value) {
    if (!value) return null;
    return typeof value === "object" ? value.value || null : value;
}

function openRegister(row) {
    formError.value = "";
    form.worker_name = row ? row.worker_name || "" : "";
    form.passport_number = row ? row.passport_number || "" : "";
    form.nationality = row ? row.nationality || "" : "";
    form.cell_number = "";
    form.iqama_number = "";
    form.batch_row = row ? row.row : null;
    form.labour_supplier = row ? row.labour_supplier || null : null;
    form.project = row ? row.project || null : null;
    registerOpen.value = true;
}

async function doRegister() {
    if (busy.value) return;
    busy.value = "register";
    formError.value = "";
    try {
        const created = await call(API + "register_temporary_worker", {
            args: {
                worker_name: form.worker_name,
                passport_number: form.passport_number,
                nationality: linkValue(form.nationality),
                building: building.value,
                cell_number: form.cell_number || null,
                iqama_number: form.iqama_number || null,
                batch_row: form.batch_row,
                labour_supplier: form.labour_supplier,
                project: form.project,
            },
            type: "POST",
        });
        toast.create({
            type: "success",
            message: t("arrivals.registered_ok", { name: created.label }),
        });
        registerOpen.value = false;
        expectedRes.reload();
        if (!form.batch_row) query.value = form.worker_name;
        else if (query.value.trim()) searchRes.reload();
    } catch (err) {
        formError.value = apiErrorMessage(err);
    } finally {
        busy.value = "";
    }
}

function issueCustody(worker) {
    router.push({
        path: "/custody",
        query: {
            party_type: worker.party_type,
            party: worker.party,
            name: worker.label || worker.party,
            mode: "issue",
        },
    });
}

function houseWorker(worker) {
    router.push({
        path: "/beds",
        query: {
            party_type: worker.party_type,
            party: worker.party,
            name: worker.label || worker.party,
        },
    });
}

async function issueLink(worker) {
    if (busy.value) return;
    busy.value = "link";
    linkQr.value = "";
    linkUrl.value = "";
    linkError.value = "";
    try {
        const rows = await call(
            "apex.apex_core.doctype.masar_worker_token.masar_worker_token.batch_issue_worker_links",
            { args: { employees_json: JSON.stringify([worker.party]) }, type: "POST" },
        );
        const row = (rows || [])[0] || {};
        linkQr.value = row.qr || "";
        linkUrl.value = row.link || "";
        linkOpen.value = true;
        toast.create({ type: "success", message: t("arrivals.linkIssued") });
    } catch (err) {
        toast.create({ type: "error", message: apiErrorMessage(err) });
    } finally {
        busy.value = "";
    }
}

async function showSlip(worker) {
    if (busy.value) return;
    busy.value = "slip";
    slipHtml.value = "";
    slipCard.value = null;
    slipError.value = "";
    try {
        const slip = await call(API + "get_arrival_slip", {
            args: { party_type: worker.party_type, party: worker.party },
            type: "POST",
        });
        slipHtml.value = (slip && slip.html) || "";
        slipCard.value = (slip && slip.card) || null;
        if (!slipCard.value || !slipCard.value.worker_name) throw new Error(t("arrivals.slipEmpty"));
        slipOpen.value = true;
    } catch (err) {
        toast.create({ type: "error", message: apiErrorMessage(err) });
    } finally {
        busy.value = "";
    }
}

function printSlip() {
    const frame = document.createElement("iframe");
    frame.setAttribute("aria-hidden", "true");
    frame.style.position = "fixed";
    frame.style.inset = "0";
    frame.style.width = "0";
    frame.style.height = "0";
    frame.style.border = "0";
    document.body.appendChild(frame);
    const doc = frame.contentWindow.document;
    doc.open();
    doc.write(slipHtml.value);
    doc.close();
    frame.contentWindow.focus();
    frame.contentWindow.print();
    window.setTimeout(() => frame.remove(), 1000);
}
</script>

<style scoped>
.row-card {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--sp-2);
    min-block-size: 68px;
    padding: var(--sp-3) var(--sp-1);
    border-block-end: var(--border-width) solid var(--c-border);
    background: transparent;
}
.row-body {
    flex: 1;
    min-inline-size: 140px;
    display: flex;
    flex-direction: column;
}
.row-body small {
    font-size: var(--fs-xs);
    color: var(--c-muted);
}
.row-card :deep(button) {
    min-block-size: var(--tap-min);
}
.link-qr {
    inline-size: 200px;
    block-size: 200px;
    margin-inline: auto;
    display: block;
}
.break {
    word-break: break-all;
}
.slip {
    max-height: 60vh;
    overflow: auto;
    background: var(--c-surface-2);
    color: var(--c-ink);
    padding: var(--sp-3);
    border-radius: var(--radius-sm);
}
.sheet-actions {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
}
</style>
