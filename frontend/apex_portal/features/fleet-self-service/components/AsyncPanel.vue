<script setup>
import { Button } from "frappe-ui";
import PortalSkeleton from "../../../components/PortalSkeleton.vue";
defineProps({ state: { type: String, default: "ready" }, title: String, message: String });
defineEmits(["retry"]);
</script>

<template>
    <PortalSkeleton v-if="state === 'loading'" :rows="3" :label="title || 'جارٍ تحميل البيانات'" />
    <section v-else-if="state !== 'ready'" class="salis-state" :data-state="state" role="status">
        <span class="salis-state__mark" aria-hidden="true">{{
            state === "loading" ? "•••" : state === "error" ? "!" : "—"
        }}</span>
        <h2>{{ title }}</h2>
        <p>{{ message }}</p>
        <Button
            v-if="state === 'error'"
            variant="outline"
            label="حاول مرة ثانية"
            @click="$emit('retry')"
        />
    </section>
    <slot v-else />
</template>
