<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- Loading placeholder: shimmer blocks shaped like the real content, shown while
     a token-scoped resource is in flight (replaces a bare "Loading..." line).

       variant="card"  (default) a card-shaped block: an avatar + title line, then
                       `lines` body lines (last one short). Wrapped in .card.card-pad.
       variant="stats" a row of `lines` stat tiles (mirrors the .stat grids).
       variant="lines" just the shimmer lines, no card chrome.

     All shimmer comes from the global .sk-* rules in index.css — the animation is a
     moving background-position sweep, so it is RTL-safe with NO direction-keyed
     selector (avoids the scoped [dir=rtl] pitfall, T-297). aria-hidden: a purely
     decorative placeholder, not announced. -->
<template>
  <div v-if="variant === 'stats'" class="grid gap-3" :class="`grid-cols-${lines}`" aria-hidden="true">
    <div v-for="n in lines" :key="n" class="stat">
      <div class="sk-line sk-w-50" style="height: 10px"></div>
      <div class="sk-line sk-w-70" style="height: 18px; margin-top: 8px"></div>
    </div>
  </div>

  <div v-else-if="variant === 'lines'" class="space-y-3" aria-hidden="true">
    <div v-for="n in lines" :key="n" class="sk-line" :class="n === lines && lines > 1 ? 'sk-w-60' : ''"></div>
  </div>

  <div v-else class="card card-pad" aria-hidden="true">
    <div class="flex items-center gap-3">
      <div class="sk-block sk-avatar"></div>
      <div class="min-w-0 flex-1 space-y-2">
        <div class="sk-line sk-w-70"></div>
        <div class="sk-line sk-w-40"></div>
      </div>
    </div>
    <div class="space-y-3" style="margin-top: 16px">
      <div v-for="n in lines" :key="n" class="sk-line" :class="n === lines && lines > 1 ? 'sk-w-60' : ''"></div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  // "card" (default) | "stats" | "lines"
  variant: { type: String, default: "card" },
  // card: number of body lines; stats: number of tiles; lines: number of lines.
  lines: { type: Number, default: 3 },
});
</script>
