<!-- Copyright (c) 2026, afmcoltd -->
<template>
    <div class="section-head">
        <h2>{{ t("arrivals.expected") }}</h2>
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
    </div>

    <ListSkeleton
        v-if="expectedRes.loading && !manifest.total"
        :rows="4"
        :label="t('common.loading')"
    />

    <LoadError
        v-else-if="expectedRes.error"
        :title="t('errors.arrivalsFailed')"
        :detail="expectedErrorMessage"
        :hint="t('errors.retryHint')"
        :retry-label="t('common.retry')"
        @retry="expectedRes.reload()"
    />

    <EmptyState v-else-if="!manifest.workers.length" :title="t('arrivals.expectedEmpty')">
        <template #icon><Icon name="calendar" :size="24" /></template>
    </EmptyState>

    <ul v-else class="stack-tight">
        <li v-for="row in manifest.workers" :key="row.row" class="row-card">
            <div class="row-body">
                <b>{{ row.worker_name }}</b>
                <small
                    >{{ row.passport_number }} · {{ row.nationality || t("common.none") }}</small
                >
            </div>
            <span v-if="row.arrived" class="pill pill-success">{{
                t("arrivals.registered")
            }}</span>
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

    <div class="section-head">
        <h2>{{ t("arrivals.searchWorker") }}</h2>
        <Button
            size="lg"
            variant="outline"
            :disabled="!canRegister"
            :label="t('arrivals.registerTitle')"
            @click="openRegister(null)"
        >
            <template #prefix><Icon name="plus" :size="18" /></template>
        </Button>
    </div>

    <FormControl type="text" size="lg" :label="t('common.search')" v-model="query" />

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
                size="lg"
                variant="ghost"
                :label="t('arrivals.slipCta')"
                @click="showSlip(w)"
            />
            <Button
                v-if="w.party_type === 'Employee'"
                size="lg"
                variant="ghost"
                :label="t('arrivals.linkCta')"
                @click="issueLink(w)"
            />
        </li>
    </ul>
    <!-- A failed search is NOT an empty one. Rendering searchEmpty for both told the clerk
         no worker by that name exists, so they retyped it, tried the passport number, and
         went and reported the worker missing from the system. -->
    <p v-else-if="searchRes.error" class="status-note status-err">
        {{ resourceErrorMessage(searchRes.error, "errors.searchFailed") }}
    </p>
    <p v-else-if="query.trim() && !searchRes.loading" class="hint">
        {{ t("arrivals.searchEmpty") }}
    </p>

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
                <!-- 300 countries cannot be found in a plain select: no search, and on a
                     phone the list cannot even be scrolled to the end. Autocomplete is the
                     library's own control for a long list. -->
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
            <div class="slip" v-html="slipHtml"></div>
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
import EmptyState from "@shared/components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import ListSkeleton from "../components/ListSkeleton.vue";
import LoadError from "../components/LoadError.vue";
import { call } from "@shared/call";
import { useI18n, apiErrorMessage, resourceErrorMessage } from "../i18n";
import { can } from "../portal.js";
import { building, localDate } from "../session";

const { t, tEnum } = useI18n();
const router = useRouter();

const API = "apex.habitat.api.arrivals_desk.";
const canRegister = can("register_worker");

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
const slipError = ref("");

const form = reactive({
    worker_name: "",
    passport_number: "",
    nationality: "",
    cell_number: "",
    iqama_number: "",
    batch_row: null,
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

const workers = computed(() => (query.value.trim() ? searchRes.data || [] : []));

function fetchAll() {
    if (building.value) expectedRes.fetch();
}

watch(building, fetchAll);
onMounted(fetchAll);

let searchTimer = 0;
watch(query, () => {
    window.clearTimeout(searchTimer);
    if (!query.value.trim()) return;
    searchTimer = window.setTimeout(() => searchRes.fetch(), 250);
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
            },
            type: "POST",
        });
        toast.create({
            type: "success",
            message: t("arrivals.registered_ok", { name: created.label }),
        });
        registerOpen.value = false;
        expectedRes.reload();
        /* A worker registered from the top button carries no manifest row, so reloading the
           expected list alone left him in NO list at all — the toast fired and not one pixel
           moved. Put him in the search results, which is the one list that can hold him. */
        if (!form.batch_row) query.value = form.worker_name;
        else if (query.value.trim()) searchRes.reload();
    } catch (err) {
        formError.value = apiErrorMessage(err);
    } finally {
        busy.value = "";
    }
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
    linkOpen.value = true;
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
        toast.create({ type: "success", message: t("arrivals.linkIssued") });
    } catch (err) {
        linkError.value = apiErrorMessage(err);
    }
}

async function showSlip(worker) {
    slipOpen.value = true;
    slipHtml.value = "";
    slipError.value = "";
    try {
        const slip = await call(API + "get_arrival_slip", {
            args: { party_type: worker.party_type, party: worker.party },
            type: "POST",
        });
        slipHtml.value = (slip && slip.html) || "";
    } catch (err) {
        slipError.value = apiErrorMessage(err);
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
