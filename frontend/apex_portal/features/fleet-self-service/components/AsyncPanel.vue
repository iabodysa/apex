<script setup>
import { FeatherIcon } from "frappe-ui";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import PortalErrorState from "../../../components/PortalErrorState.vue";
defineProps({
    state: {
        type: String,
        default: "ready",
        validator: (value) => ["ready", "loading", "error", "empty"].includes(value),
    },
    title: String,
    message: [String, Object],
});
defineEmits(["retry"]);
</script>

<template>
    <PortalSkeleton v-if="state === 'loading'" :rows="3" :label="title || 'جارٍ تحميل البيانات'" />
    <PortalErrorState
        v-else-if="state === 'error'"
        :title="title || 'تعذّر تحميل البيانات'"
        :message="message"
        @retry="$emit('retry')"
    />
    <section v-else-if="state === 'empty'" class="salis-state" :data-state="state" role="status">
        <span class="salis-state__mark" aria-hidden="true">
            <slot name="icon"><FeatherIcon name="inbox" :stroke-width="1.75" /></slot>
        </span>
        <h2>{{ title }}</h2>
        <p>{{ message }}</p>
        <slot name="action" />
    </section>
    <slot v-else />
</template>
