<script setup>
import { Button } from "frappe-ui";
defineProps({ state: { type: String, default: "ready" }, title: String, message: String });
defineEmits(["retry"]);
</script>

<template>
    <section v-if="state !== 'ready'" class="salis-state" :data-state="state" role="status">
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
