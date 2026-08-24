<script setup>
import { computed, onMounted } from "vue";
import { Badge, Button } from "frappe-ui";
import AsyncPanel from "./AsyncPanel.vue";
import { recordTitle, statusLabel, statusTheme } from "../../../core/displayLabels.js";
import { __ } from "../../../core/i18n.js";

const props = defineProps({
    title: { type: String, required: true },
    resource: { type: Object, required: true },
    rowsKey: { type: String, default: "" },
    empty: String,
    createTo: String,
});
const rows = computed(() => {
    const data = props.resource.data;
    if (props.rowsKey) return data?.[props.rowsKey] || [];
    return Array.isArray(data) ? data : [];
});
onMounted(() => props.resource.fetch());
</script>

<template>
    <section class="salis-page">
        <header class="salis-page__heading">
            <div>
                <p class="salis-eyebrow">{{ __("Salis") }}</p>
                <h2>{{ title }}</h2>
            </div>
            <Button
                variant="ghost"
                icon="lucide-refresh-cw"
                :label="__('Refresh')"
                :loading="resource.loading"
                @click="resource.fetch()"
            />
        </header>
        <RouterLink v-if="createTo" class="salis-primary-link" :to="createTo"
            >{{ __("Add New") }}</RouterLink
        >
        <AsyncPanel
            v-if="resource.loading && !rows.length"
            state="loading"
            :title="__('Loading')"
            :message="__('Retrieving the latest recorded data.')"
        />
        <AsyncPanel
            v-else-if="resource.error"
            state="error"
            :title="__('Could not load this data')"
            :message="resource.error"
            @retry="resource.fetch()"
        />
        <AsyncPanel
            v-else-if="!rows.length"
            state="empty"
            :title="__('No records')"
            :message="empty"
        >
            <template v-if="createTo" #action>
                <RouterLink class="salis-primary-link" :to="createTo">{{ __("Add New") }}</RouterLink>
            </template>
        </AsyncPanel>
        <ul v-else class="salis-list">
            <li v-for="row in rows" :key="row.name || row.id">
                <div class="record-identity">
                    <strong dir="auto">{{ recordTitle(row, ["subject", "incident_type", "type", "vehicle_plate", "project"], title) }}</strong>
                    <bdi v-if="row.name" class="record-reference" dir="auto" translate="no">{{ row.name }}</bdi>
                    <p dir="auto">
                        {{
                            row.description ||
                            row.vehicle_plate ||
                            row.location ||
                            row.project ||
                            ""
                        }}
                    </p>
                </div>
                <Badge :theme="statusTheme(row.status || 'Open')" variant="subtle" :label="statusLabel(row.status || 'Open')" />
            </li>
        </ul>
    </section>
</template>
