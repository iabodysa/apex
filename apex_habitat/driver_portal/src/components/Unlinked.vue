<template>
  <div class="flex-1 flex flex-col p-6 max-w-md mx-auto w-full">
    <header class="mb-6 flex items-center gap-2">
      <span class="text-xl font-extrabold text-ah-forest">Salis</span>
      <span class="text-[11px] font-medium px-2 py-0.5 rounded-full bg-ah-accent/30 text-ah-forest">
        Driver Portal
      </span>
    </header>

    <!-- STAFF: signed-in desk operator with no driver profile. Not an error. -->
    <section v-if="ctx.is_staff" class="space-y-5">
      <div class="bg-ah-surface rounded-ah p-5 shadow-sm">
        <div class="flex items-center gap-3">
          <span
            class="grid place-items-center h-11 w-11 rounded-full bg-ah-primary/10 text-ah-primary shrink-0"
          >
            <Icon name="user" :size="22" />
          </span>
          <div class="min-w-0">
            <div class="text-base font-semibold text-ah-forest truncate">
              {{ ctx.full_name || "Signed in" }}
            </div>
            <span
              class="inline-block mt-0.5 text-xs px-2 py-0.5 rounded-full bg-ah-accent/30 text-ah-forest"
            >
              Staff
            </span>
          </div>
        </div>
        <p class="mt-3 text-sm text-ah-forest/70">
          This mobile portal is for drivers. As staff, use your desk tools below to manage the
          fleet.
        </p>
      </div>

      <div v-if="ctx.links && ctx.links.length" class="space-y-3">
        <a
          v-for="link in ctx.links"
          :key="link.url"
          :href="link.url"
          class="flex items-center gap-3 bg-ah-surface hover:bg-white rounded-ah p-4 shadow-sm border border-ah-forest/5"
        >
          <span
            class="grid place-items-center h-9 w-9 rounded-lg bg-ah-forest text-white shrink-0"
          >
            <Icon name="dashboard" :size="18" />
          </span>
          <span class="font-medium text-ah-forest">{{ link.label }}</span>
          <Icon name="chevron" :size="18" class="ml-auto text-ah-forest/30" />
        </a>
      </div>
    </section>

    <!-- NON-STAFF, NON-DRIVER: friendly explainer + way out. -->
    <section v-else class="space-y-5">
      <div class="bg-ah-surface rounded-ah p-5 shadow-sm text-center">
        <span
          class="mx-auto grid place-items-center h-12 w-12 rounded-full bg-ah-accent/20 text-ah-primary"
        >
          <Icon name="user" :size="26" />
        </span>
        <div class="mt-3 text-base font-semibold text-ah-forest">
          Hello{{ ctx.full_name ? ", " + ctx.full_name : "" }}
        </div>
        <p class="mt-2 text-sm text-ah-forest/70">
          Your account isn't linked to a driver profile yet. If you're a driver, ask your
          supervisor to link your account.
        </p>
      </div>
      <a
        href="/app"
        class="flex items-center justify-center gap-2 bg-ah-primary text-white rounded-ah p-4 font-semibold shadow-sm active:scale-95 transition"
      >
        <Icon name="external" :size="18" /> Go to the main app
      </a>
    </section>
  </div>
</template>

<script setup>
import Icon from "./Icon.vue";

defineProps({ ctx: { type: Object, required: true } });
</script>
