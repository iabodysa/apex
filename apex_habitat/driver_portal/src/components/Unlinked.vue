<template>
  <div class="flex-1 flex flex-col px-6 py-7 mx-auto w-full" style="max-width: 480px">
    <header class="mb-6 flex items-center gap-2">
      <template v-if="showBrand">
        <img
          v-if="brandLogo"
          :src="brandLogo"
          alt="AFMCO"
          class="h-7 w-auto max-w-[120px] object-contain"
        />
        <template v-else>
          <Brand mode="mark" :size="24" primary-color="var(--c-primary)" accent-color="var(--c-mint)" />
          <span class="text-xl font-extrabold tracking-tight">AFMCO</span>
        </template>
      </template>
      <span v-else class="text-xl font-extrabold tracking-tight">Salis</span>
      <span class="pill pill-accent">Driver Portal</span>
    </header>

    <!-- STAFF: signed-in desk operator with no driver profile. Not an error. -->
    <section v-if="ctx.is_staff" class="space-y-5">
      <div class="card card-pad">
        <div class="flex items-center gap-3">
          <span
            class="avatar h-11 w-11"
            style="background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary)"
          >
            <Icon name="user" :size="22" />
          </span>
          <div class="min-w-0">
            <div class="text-base font-bold truncate">{{ ctx.full_name || "Signed in" }}</div>
            <span class="pill pill-accent mt-0.5">Staff</span>
          </div>
        </div>
        <p class="mt-3 text-sm text-soft">
          This mobile portal is for drivers. As staff, use your desk tools below to manage the
          fleet.
        </p>
      </div>

      <div v-if="ctx.links && ctx.links.length" class="space-y-3">
        <a
          v-for="link in ctx.links"
          :key="link.url"
          :href="link.url"
          class="card card-pad flex items-center gap-3"
          style="text-decoration: none"
        >
          <span
            class="avatar h-9 w-9"
            style="border-radius: var(--radius-sm); background: var(--c-ink); color: var(--c-surface)"
          >
            <Icon name="dashboard" :size="18" />
          </span>
          <span class="font-semibold">{{ link.label }}</span>
          <Icon name="chevron" :size="18" class="ml-auto text-muted" />
        </a>
      </div>
    </section>

    <!-- NON-STAFF, NON-DRIVER: friendly explainer + way out. -->
    <section v-else class="space-y-5">
      <div class="card card-pad text-center">
        <span
          class="avatar mx-auto h-12 w-12"
          style="background: color-mix(in srgb, var(--c-mint) 22%, transparent); color: var(--c-primary)"
        >
          <Icon name="user" :size="26" />
        </span>
        <div class="mt-3 text-base font-bold">
          Hello{{ ctx.full_name ? ", " + ctx.full_name : "" }}
        </div>
        <p class="mt-2 text-sm text-soft">
          Your account isn't linked to a driver profile yet. If you're a driver, ask your
          supervisor to link your account.
        </p>
      </div>
      <a href="/app" class="btn btn-primary" style="text-decoration: none">
        <Icon name="external" :size="18" /> Go to the main app
      </a>
    </section>
  </div>
</template>

<script setup>
import Icon from "./Icon.vue";
import Brand from "./Brand.vue";

defineProps({
  ctx: { type: Object, required: true },
  showBrand: { type: Boolean, default: true },
  brandLogo: { type: String, default: "" },
});
</script>
