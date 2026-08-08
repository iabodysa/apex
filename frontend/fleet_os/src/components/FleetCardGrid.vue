<!-- Copyright (c) 2026, afmcoltd -->
<template>
  <div class="cards-wrap">
    <EmptyBoard v-if="!filtered.length" icon="car" />

    <div v-else class="cards-grid" :class="{ 'fp-compact': density === 'compact' }">
      <!-- A vehicle card is domain-specific: plate, state, holder, incident stripes and the
           actions that change the state, all in one scannable block. The library has no
           equivalent, so the card stays ours — every control inside it does not. -->
      <article
        v-for="v in filtered"
        :key="v.plate"
        class="vcard"
        :class="['vs-' + v.vehicle_status, { 'fp-sel': selectMode && isSelected(v.plate), 'fp-busy': isBusy(v.plate) }]"
      >
        <div class="vc-top">
          <div class="vc-id">
            <Checkbox
              v-if="selectMode"
              :model-value="isSelected(v.plate)"
              :label="t('bulk.selectOne', { plate: v.plate })"
              class="fp-sel-box"
              @update:model-value="toggleSelect(v.plate)"
            />
            <button type="button" class="vc-plate" @click="openVehicle(v.plate)">
              <bdi>{{ v.plate }}</bdi>
            </button>
          </div>
          <div class="vc-icon-area">
            <span class="vc-sheet-icon"><Icon :name="fmt.icon(v)" :size="24" /></span>
            <span class="vc-fuel-badge">{{ fmt.trim(v.fuel) || t("common.none") }}</span>
          </div>
        </div>

        <div class="vc-status-bar">
          <Badge :theme="fmt.sb(v).theme" size="md" :label="fmt.sb(v).label" />
          <span v-if="v.vehicle_status === 'workshop' && v.workshop_date" class="vc-meta-note">
            <Icon name="calendar" :size="11" /> <bdi>{{ v.workshop_date }}</bdi>
          </span>
          <span v-else-if="v.vehicle_status !== 'assigned'" class="vc-meta-note">
            {{ t("card.prevDrivers", { n: v.history.length }) }}
          </span>
        </div>

        <div v-if="v.current_driver" class="vc-driver">
          <span class="drv-av">{{ fmt.initials(v.current_driver) }}</span>
          <span class="drv-info">
            <span class="drv-name">
              {{ v.current_driver.name_ar || v.current_driver.name_en || t("common.none") }}
            </span>
            <span class="drv-since">
              {{ t("card.since") }} <bdi>{{ v.current_driver.date_receive || t("common.none") }}</bdi>
              · {{ fmt.trim(v.current_driver.project) || t("common.none") }}
            </span>
          </span>
          <Icon name="lock" :size="15" />
        </div>
        <div v-else class="no-driver">
          <template v-if="v.vehicle_status === 'available'">
            <Icon name="key" :size="14" /> {{ t("card.readyToAssign") }}
          </template>
          <template v-else-if="v.vehicle_status === 'workshop'">
            <Icon name="wrench" :size="14" /> {{ t("card.inMaintenance") }}
          </template>
          <template v-else><Icon name="circle-pause" :size="14" /> {{ t("card.outOfService") }}</template>
        </div>

        <div
          v-if="fmt.expiryFlag(v).show"
          class="vc-stripe"
          :class="fmt.expiryFlag(v).expired ? 'vc-stripe-danger' : 'vc-stripe-warn'"
        >
          <Icon name="shield-alert" :size="13" />
          <span>{{ fmt.expiryFlag(v).label }}</span>
          <bdi v-if="fmt.expiryFlag(v).date" class="vc-stripe-date">{{ fmt.expiryFlag(v).date }}</bdi>
        </div>
        <div v-if="v.vehicle_status === 'workshop'" class="vc-stripe vc-stripe-warn">
          <Icon name="wrench" :size="13" /> {{ v.workshop_notes || t("card.inMaintenance") }}
        </div>
        <div v-if="v.vehicle_status === 'stolen'" class="vc-stripe vc-stripe-danger">
          <Icon name="shield-alert" :size="13" /> {{ t("card.stolen") }}
          <template v-if="v.stolen_info && v.stolen_info.date">· <bdi>{{ v.stolen_info.date }}</bdi></template>
        </div>

        <div v-if="v.damages.length || v.accidents.length" class="vc-incidents">
          <Badge v-if="v.damages.length" theme="red" size="sm" :label="t('card.damageCount', { n: v.damages.length })" />
          <Badge v-if="v.accidents.length" theme="orange" size="sm" :label="t('card.accidentCount', { n: v.accidents.length })" />
        </div>

        <div class="vc-meta">
          <div class="vc-type">{{ v.vehicle_type || t("common.none") }}</div>
          <div class="vc-office">
            <Icon name="building" :size="12" /> {{ v.rental_office || t("common.none") }}
            · {{ fmt.trim(v.project) || t("common.none") }}
            · <Icon name="pin" :size="12" /> {{ v.area || t("common.none") }}
          </div>
        </div>

        <div v-if="fmt.calcTotalDaysNum(v) > 0" class="vc-dur">
          <div class="dur-label">
            <span>{{ t("card.totalRunning", { n: fmt.calcTotalDaysNum(v) }) }}</span>
            <bdi>{{ v.history.length ? v.history[0].date_receive || "" : "" }}</bdi>
          </div>
          <Progress :value="runPct(v)" size="sm" />
        </div>

        <div class="vc-actions">
          <template v-if="v.vehicle_status === 'assigned'">
            <Button variant="outline" theme="red" size="lg" :disabled="isBusy(v.plate)" :label="t('card.stop')" @click="actions.quickStop(v.plate)" />
            <Button variant="outline" theme="green" size="lg" :disabled="isBusy(v.plate)" :label="t('card.reassign')" @click="actions.quickReassign(v.plate)" />
            <Button variant="outline" size="lg" :disabled="isBusy(v.plate)" :label="t('card.workshop')" @click="actions.quickStop(v.plate, true)" />
          </template>
          <template v-else-if="v.vehicle_status === 'available'">
            <Button variant="outline" theme="green" size="lg" :disabled="isBusy(v.plate)" :label="t('card.assign')" @click="actions.quickReassign(v.plate)" />
            <Button variant="outline" size="lg" :disabled="isBusy(v.plate)" :label="t('card.workshop')" @click="actions.sendWorkshop(v.plate)" />
            <Button variant="ghost" theme="red" size="lg" :disabled="isBusy(v.plate)" :label="t('card.markStolen')" @click="actions.markStolen(v.plate)" />
          </template>
          <template v-else-if="v.vehicle_status === 'workshop'">
            <Button variant="outline" theme="green" size="lg" :disabled="isBusy(v.plate)" :label="t('card.exit')" @click="actions.exitWorkshop(v.plate)" />
            <Button variant="outline" size="lg" :disabled="isBusy(v.plate)" :label="t('card.assign')" @click="actions.quickReassign(v.plate)" />
          </template>
          <template v-else-if="v.vehicle_status === 'stolen'">
            <Button variant="outline" theme="green" size="lg" :disabled="isBusy(v.plate)" :label="t('card.recover')" @click="actions.recoverVehicle(v.plate)" />
          </template>
          <template v-else>
            <Button variant="outline" theme="green" size="lg" :disabled="isBusy(v.plate)" :label="t('card.available')" @click="actions.setAvailable(v.plate)" />
            <Button variant="outline" size="lg" :disabled="isBusy(v.plate)" :label="t('card.workshop')" @click="actions.sendWorkshop(v.plate)" />
          </template>
          <Button variant="ghost" size="lg" :tooltip="t('card.historyTitle')" :label="t('card.history', { n: v.history.length })" @click="openVehicle(v.plate, 'log')" />
        </div>
      </article>
    </div>
  </div>
</template>

<script setup>
import { Badge, Button, Checkbox, Progress } from "frappe-ui";

import Icon from "../Icon.vue";
import EmptyBoard from "./EmptyBoard.vue";
import { useBoardContext } from "../boardContext.js";

const { t, fmt, state, filters, selection, actions, density } = useBoardContext();
const { filtered } = filters;
const { selectMode, isSelected, toggleSelect } = selection;
const { isBusy } = actions;
const { openVehicle } = state;

/* A year and a bit of continuous running fills the bar; beyond that the number beside it is
   what carries the meaning, so the bar simply stays full. */
const runPct = (v) => Math.min(100, Math.round((fmt.calcTotalDaysNum(v) / 400) * 100));
</script>
