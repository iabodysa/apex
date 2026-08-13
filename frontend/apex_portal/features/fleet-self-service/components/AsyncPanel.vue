<script setup>
import { Button } from "frappe-ui";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
import PortalErrorState from "../../../components/PortalErrorState.vue";
defineProps({ state: { type: String, default: "ready" }, title: String, message: [String, Object] });
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
    <section v-else-if="state !== 'ready'" class="salis-state" :data-state="state" role="status">
        <span class="salis-state__mark" aria-hidden="true">{{
            state === "loading" ? "•••" : state === "error" ? "!" : "—"
        }}</span>
        <h2>{{ title }}</h2>
        <p>{{ message }}</p>
    </section>
    <slot v-else />
</template>
