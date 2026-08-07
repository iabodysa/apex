<!-- Copyright (c) 2026, afmcoltd -->
<script setup>
import Icon from "./Icon.vue";
defineProps([
  "filtered", "density", "isScopeEmpty", "anyFilterActive", "activeFilterChips",
  "selectMode", "resetFilters", "isSelected", "toggleSelect", "isBusy", "openPanel",
  "sb", "icon", "trim", "initials", "expiryFlag", "calcTotalDaysNum",
  "quickStop", "quickReassign", "sendWorkshop", "exitWorkshop",
  "setAvailable", "recoverVehicle", "markStolen", "t",
]);
</script>

<template>
  <div class="cards-wrap">
        <div v-if="!filtered.length" class="empty">
          <div class="empty-ic"><Icon :name="isScopeEmpty ? 'lock' : 'car'" :size="42" :stroke-width="1.5" /></div>
          <div>{{ isScopeEmpty ? t("main.noScope") : anyFilterActive ? t("main.noResultsFilters") : t("main.noVehicles") }}</div>
          <div v-if="!isScopeEmpty && activeFilterChips.length" class="fp-empty-filters">
            {{ t("main.activeFilters") }}
            <span class="fp-chip" v-for="(c, i) in activeFilterChips" :key="i">{{ c }}</span>
          </div>
          <button v-if="!isScopeEmpty && anyFilterActive" class="btn btn-blue" @click="resetFilters">{{ t("main.clearFilters") }}</button>
        </div>
        <div v-else class="cards-grid" :class="{ 'fp-compact': density === 'compact' }">
          <div
            v-for="v in filtered"
            :key="v.plate"
            class="vcard"
            :class="['vs-' + v.vehicle_status, { 'fp-sel': selectMode && isSelected(v.plate), 'fp-busy': isBusy(v.plate) }]"
            @click="selectMode ? toggleSelect(v.plate) : openPanel(v.plate)"
          >
            <div class="vc-top">
              <div style="display:flex;align-items:center;gap:8px">
                <input v-if="selectMode" type="checkbox" class="fp-sel-box" :checked="isSelected(v.plate)" @click.stop="toggleSelect(v.plate)" />
                <div class="vc-plate"><bdi>{{ v.plate }}</bdi></div>
              </div>
              <div class="vc-icon-area">
                <span class="vc-sheet-icon"><Icon :name="icon(v)" :size="24" /></span>
                <span class="vc-fuel-badge">{{ trim(v.fuel) || "—" }}</span>
              </div>
            </div>
            <div class="vc-status-bar">
              <span class="sbadge" :class="sb(v).cls"><Icon :name="sb(v).ic" :size="13" />{{ sb(v).label }}</span>
              <span v-if="v.vehicle_status === 'workshop' && v.workshop_date" style="font-size:10px;color:var(--orange-l);font-family:'JetBrains Mono',monospace;display:inline-flex;align-items:center;gap:3px"><Icon name="calendar" :size="11" /> <bdi>{{ v.workshop_date }}</bdi></span>
              <span v-else-if="v.vehicle_status !== 'assigned' && v.vehicle_status !== 'workshop'" style="font-size:10px;color:var(--t3)">{{ t("card.prevDrivers", { n: v.history.length }) }}</span>
            </div>
            <div v-if="v.current_driver" class="vc-driver">
              <div class="drv-av">{{ initials(v.current_driver) }}</div>
              <div class="drv-info">
                <div class="drv-name">{{ v.current_driver.name_ar || v.current_driver.name_en || t("common.none") }}</div>
                <div class="drv-since">{{ t("card.since") }} <bdi>{{ v.current_driver.date_receive || t("common.none") }}</bdi> · {{ trim(v.current_driver.project) || t("common.none") }}</div>
              </div>
              <span class="lock-ico"><Icon name="lock" :size="15" /></span>
            </div>
            <div v-else class="no-driver">
              <template v-if="v.vehicle_status === 'available'"><Icon name="key" :size="14" /> {{ t("card.readyToAssign") }}</template>
              <template v-else-if="v.vehicle_status === 'workshop'"><Icon name="wrench" :size="14" /> {{ t("card.inMaintenance") }}</template>
              <template v-else><Icon name="circle-pause" :size="14" /> {{ t("card.outOfService") }}</template>
            </div>
            <div
              v-if="expiryFlag(v).show"
              class="vc-expiry-stripe"
              :class="expiryFlag(v).expired ? 'vc-expiry-expired' : 'vc-expiry-soon'"
            >
              <Icon name="shield-alert" :size="13" />
              <span>{{ expiryFlag(v).label }}</span>
              <bdi v-if="expiryFlag(v).date" class="vc-expiry-date">{{ expiryFlag(v).date }}</bdi>
            </div>
            <div v-if="v.vehicle_status === 'workshop'" class="vc-workshop-stripe"><Icon name="wrench" :size="13" /> {{ v.workshop_notes || t("card.inMaintenance") }}</div>
            <div v-if="v.vehicle_status === 'stolen'" class="vc-stolen-stripe"><Icon name="shield-alert" :size="13" /> {{ t("card.stolen") }} <template v-if="v.stolen_info && v.stolen_info.date">· <bdi>{{ v.stolen_info.date }}</bdi></template></div>
            <div v-if="(v.damages || []).length || (v.accidents || []).length" style="padding:3px 14px;display:flex;gap:6px;border-top:1px solid var(--b1)">
              <span v-if="(v.damages || []).length" style="font-size:10px;padding:2px 7px;background:var(--red-d);color:var(--red-l);border-radius:6px;border:1px solid color-mix(in srgb,var(--c-danger) 20%,transparent);display:inline-flex;align-items:center;gap:3px"><Icon name="hammer" :size="11" /> {{ t("card.damageCount", { n: v.damages.length }) }}</span>
              <span v-if="(v.accidents || []).length" style="font-size:10px;padding:2px 7px;background:var(--amber-d);color:var(--amber-l);border-radius:6px;border:1px solid color-mix(in srgb,var(--c-warning) 20%,transparent);display:inline-flex;align-items:center;gap:3px"><Icon name="crash" :size="11" /> {{ t("card.accidentCount", { n: v.accidents.length }) }}</span>
            </div>
            <div class="vc-meta vc-meta-demoted">
              <div class="vc-type">{{ v.vehicle_type || "—" }}</div>
              <div class="vc-office"><Icon name="building" :size="12" /> {{ v.rental_office }} &middot; {{ trim(v.project) || "—" }} &middot; <Icon name="pin" :size="12" /> {{ v.area }}</div>
            </div>
            <div v-if="calcTotalDaysNum(v) > 0" class="vc-dur">
              <div class="dur-label">
                <span>{{ t("card.totalRunning", { n: calcTotalDaysNum(v) }) }}</span>
                <span><bdi>{{ v.history.length ? v.history[0].date_receive || "" : "" }}</bdi></span>
              </div>
              <div class="dur-bar"><div class="dur-fill" :style="{ width: Math.min(100, Math.round((calcTotalDaysNum(v) / 400) * 100)) + '%' }"></div></div>
            </div>
            <div class="vc-actions" :class="{ 'fp-actions-busy': isBusy(v.plate) }" @click.stop>
              <span v-if="isBusy(v.plate)" class="fp-action-spin" :aria-label="t('card.working')"></span>
              <template v-if="v.vehicle_status === 'assigned'">
                <button class="ac ac-stop" :disabled="isBusy(v.plate)" :title="t('card.stopTitle')" @click="quickStop(v.plate)"><span class="ac-ico"><Icon name="circle-pause" :size="14" /></span>{{ t("card.stop") }}</button>
                <button class="ac ac-reassign" :disabled="isBusy(v.plate)" :title="t('card.reassignTitle')" @click="quickReassign(v.plate)"><span class="ac-ico"><Icon name="rotate-cw" :size="14" /></span>{{ t("card.reassign") }}</button>
                <button class="ac ac-workshop" :disabled="isBusy(v.plate)" :title="t('card.sendWorkshopAfterStopTitle')" @click="quickStop(v.plate, true)"><span class="ac-ico"><Icon name="wrench" :size="14" /></span>{{ t("card.workshop") }}</button>
              </template>
              <template v-else-if="v.vehicle_status === 'available'">
                <button class="ac ac-free" :disabled="isBusy(v.plate)" :title="t('card.assignNewTitle')" @click="quickReassign(v.plate)"><span class="ac-ico"><Icon name="key" :size="14" /></span>{{ t("card.assign") }}</button>
                <button class="ac ac-workshop" :disabled="isBusy(v.plate)" :title="t('card.sendWorkshopTitle')" @click="sendWorkshop(v.plate)"><span class="ac-ico"><Icon name="wrench" :size="14" /></span>{{ t("card.workshop") }}</button>
              </template>
              <template v-else-if="v.vehicle_status === 'workshop'">
                <button class="ac ac-free" :disabled="isBusy(v.plate)" :title="t('card.exitWorkshopTitle')" @click="exitWorkshop(v.plate)"><span class="ac-ico"><Icon name="circle-check" :size="14" /></span>{{ t("card.exit") }}</button>
                <button class="ac ac-reassign" :disabled="isBusy(v.plate)" :title="t('card.assignDirectTitle')" @click="quickReassign(v.plate)"><span class="ac-ico"><Icon name="key" :size="14" /></span>{{ t("card.assign") }}</button>
              </template>
              <template v-else>
                <button class="ac ac-free" :disabled="isBusy(v.plate)" :title="t('card.setAvailableTitle')" @click="setAvailable(v.plate)"><span class="ac-ico"><Icon name="circle-dot" :size="14" /></span>{{ t("card.available") }}</button>
                <button class="ac ac-workshop" :disabled="isBusy(v.plate)" :title="t('card.sendWorkshopTitle')" @click="sendWorkshop(v.plate)"><span class="ac-ico"><Icon name="wrench" :size="14" /></span>{{ t("card.workshop") }}</button>
              </template>
              <button v-if="v.vehicle_status === 'stolen'" class="ac" style="border-color:color-mix(in srgb,var(--purple) 25%,transparent);color:var(--purple-l)" :disabled="isBusy(v.plate)" :title="t('card.recoverTitle')" @click="recoverVehicle(v.plate)"><span class="ac-ico"><Icon name="lock-open" :size="14" /></span>{{ t("card.recover") }}</button>
              <button v-else-if="v.vehicle_status === 'available'" class="ac" style="border-color:color-mix(in srgb,var(--c-danger) 25%,transparent);color:var(--red-l)" :disabled="isBusy(v.plate)" :title="t('card.markStolenTitle')" @click="markStolen(v.plate)"><span class="ac-ico"><Icon name="shield-alert" :size="14" /></span>{{ t("card.markStolen") }}</button>
              <button class="ac ac-hist" :title="t('card.historyTitle')" @click="openPanel(v.plate, 5)"><span class="ac-ico"><Icon name="clipboard-list" :size="14" /></span><span class="hist-n">{{ v.history.length }}</span></button>
            </div>
          </div>
        </div>
  </div>
</template>
