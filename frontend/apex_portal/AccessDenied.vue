<script setup>
import { ar } from "./i18n/ar.js";
</script>

<template>
  <section class="access-denied" aria-labelledby="access-denied-title">
    <h2 id="access-denied-title">{{ ar.accessDeniedTitle }}</h2>
    <p>{{ ar.accessDeniedBody }}</p>
  </section>
</template>
