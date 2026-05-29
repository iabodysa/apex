<template>
  <div class="flex-1 flex flex-col p-6">
    <header class="mb-6">
      <div class="text-xl font-extrabold text-ah-forest">Salis</div>
      <div class="text-sm text-ah-forest/60">Driver Portal</div>
    </header>

    <!-- STAFF: signed-in desk operator with no driver profile. Not an error. -->
    <section v-if="ctx.is_staff" class="space-y-5">
      <div class="bg-ah-surface rounded-xl p-5 shadow-sm">
        <div class="text-base font-semibold text-ah-forest">
          You're signed in as {{ ctx.full_name }}
        </div>
        <div class="mt-1 inline-block text-xs px-2 py-0.5 rounded bg-ah-accent/30 text-ah-forest">
          Staff
        </div>
        <p class="mt-3 text-sm text-ah-forest/70">
          This mobile portal is for drivers. As staff, use the desk tools below to
          manage the fleet.
        </p>
      </div>

      <div v-if="ctx.links && ctx.links.length" class="space-y-3">
        <a
          v-for="link in ctx.links"
          :key="link.url"
          :href="link.url"
          class="block bg-ah-forest text-white rounded-xl p-4 text-center font-medium"
        >
          {{ link.label }}
        </a>
      </div>
    </section>

    <!-- NON-STAFF, NON-DRIVER: friendly explainer + way out. -->
    <section v-else class="space-y-5">
      <div class="bg-ah-surface rounded-xl p-5 shadow-sm">
        <div class="text-base font-semibold text-ah-forest">
          Hello{{ ctx.full_name ? ", " + ctx.full_name : "" }}
        </div>
        <p class="mt-3 text-sm text-ah-forest/70">
          Your account isn't linked to a driver profile, so there's nothing to
          show here yet. If you're a driver, ask your supervisor to link your
          account. Otherwise, head to the main app.
        </p>
      </div>
      <a
        href="/app"
        class="block bg-ah-primary text-white rounded-xl p-4 text-center font-medium"
      >
        Go to the main app
      </a>
    </section>
  </div>
</template>

<script setup>
defineProps({ ctx: { type: Object, required: true } });
</script>
