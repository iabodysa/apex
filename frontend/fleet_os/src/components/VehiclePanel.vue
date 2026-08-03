<!-- Copyright (c) 2026, AFMCO and contributors -->
<!-- Right-hand detail drawer: 6 tabs + the reassign/stop/stolen sub-forms. -->
<script setup>
import Icon from "./Icon.vue";
defineProps([
  "panel", "subForm", "closePanel", "setPTab", "tabDmg", "tabAcc", "closeSubForm",
  "sb", "initials", "calcTotalDaysNum", "calcActiveDaysNum", "fuelView", "trim",
  "historyItems", "calcDur", "today",
  "openStopForm", "openReassignForm", "sf", "confirmStop",
  "dp", "onDriverQuery", "pickDriver", "openNewDriverForm", "rf", "submitReassign",
  "changeStatus", "stf", "submitStolen", "openStolenForm", "recoverVehicle", "t",
]);
</script>

<template>
  <!-- PANEL (right drawer) -->
  <transition name="fp-overlay">
    <!-- Backdrop only duplicates the labelled close button, so it is hidden from AT. -->
    <div v-if="panel.open" class="panel-overlay open" aria-hidden="true" @click.self="closePanel"></div>
  </transition>
  <transition name="fp-panel">
    <div v-if="panel.open && panel.vehicle" class="panel" style="display:flex">
      <div class="panel-head">
        <div class="ph-left">
          <div class="ph-plate"><bdi>{{ panel.vehicle.plate }}</bdi></div>
          <div class="ph-sub">{{ panel.vehicle.vehicle_type }} · {{ panel.vehicle.rental_office }} · <Icon :name="panel.vehicle.sheet === 'CAR' ? 'car' : 'bike'" :size="13" /> {{ panel.vehicle.sheet === "CAR" ? t("sheet.car") : t("sheet.bike") }}</div>
          <div class="ph-tags">
            <span class="tag">{{ trim(panel.vehicle.fuel) || t("common.none") }}</span>
            <span class="tag">{{ trim(panel.vehicle.project) || t("panel.noProject") }}</span>
            <span class="tag"><Icon name="pin" :size="11" /> {{ trim(panel.vehicle.area) || t("common.none") }}</span>
            <span class="sbadge" :class="sb(panel.vehicle).cls" style="font-size:10px;display:inline-flex;gap:4px"><Icon :name="sb(panel.vehicle).ic" :size="11" />{{ sb(panel.vehicle).label }}</span>
          </div>
        </div>
        <!-- Icon-only: IconBase marks its svg aria-hidden, so the name must come from aria-label. -->
        <button class="panel-close" :aria-label="t('panel.close')" @click="closePanel"><Icon name="x" :size="18" /></button>
      </div>
      <div class="panel-tabs" style="flex-wrap:wrap">
        <button class="ptab" :class="{ on: panel.tab === 0 }" @click="setPTab(0)"><Icon name="home" :size="14" /> {{ t("panel.overview") }}</button>
        <button class="ptab" :class="{ on: panel.tab === 1 }" @click="setPTab(1)"><Icon name="user" :size="14" /> {{ t("panel.driver") }}</button>
        <button class="ptab" :class="{ on: panel.tab === 2 }" @click="setPTab(2)"><Icon name="settings" :size="14" /> {{ t("panel.status") }}</button>
        <button class="ptab" :class="{ on: panel.tab === 3 }" @click="setPTab(3)"><Icon name="hammer" :size="14" /> {{ t("panel.damages") }}<span v-if="tabDmg" class="ptab-badge">{{ tabDmg }}</span></button>
        <button class="ptab" :class="{ on: panel.tab === 4 }" @click="setPTab(4)"><Icon name="crash" :size="14" /> {{ t("panel.accidents") }}<span v-if="tabAcc" class="ptab-badge" style="background:var(--amber-l)">{{ tabAcc }}</span></button>
        <button class="ptab" :class="{ on: panel.tab === 5 }" @click="setPTab(5)"><Icon name="clipboard-list" :size="14" /> {{ t("panel.log") }}</button>
      </div>
      <div class="panel-body">
        <!-- TAB 0: OVERVIEW -->
        <div v-if="panel.tab === 0" class="pb on">
          <div class="psect-title"><Icon name="chart-column" :size="14" /> {{ t("panel.vehicleStats") }}</div>
          <div class="pstats">
            <div class="pstat"><div class="pstat-n" style="color:var(--purple-l)">{{ panel.vehicle.history.length }}</div><div class="pstat-l">{{ t("panel.totalDrivers") }}</div></div>
            <div class="pstat"><div class="pstat-n" style="color:var(--amber-l)">{{ calcTotalDaysNum(panel.vehicle) }}</div><div class="pstat-l">{{ t("panel.runningDays") }}</div></div>
            <div class="pstat"><div class="pstat-n" style="color:var(--green-l)">{{ calcActiveDaysNum(panel.vehicle) }}</div><div class="pstat-l">{{ t("panel.activeDays") }}</div></div>
            <div class="pstat"><div class="pstat-n" style="color:var(--cyan-l)">{{ panel.vehicle.history.filter((h) => h.status === "Active").length }}</div><div class="pstat-l">{{ t("panel.activations") }}</div></div>
          </div>
          <div class="psect-title"><Icon name="search" :size="14" /> {{ t("panel.vehicleDetails") }}</div>
          <div class="kv-grid">
            <div class="kv"><div class="kv-l">{{ t("panel.plate") }}</div><div class="kv-v mono" style="font-size:16px;letter-spacing:2px"><bdi>{{ panel.vehicle.plate }}</bdi></div></div>
            <div class="kv"><div class="kv-l">{{ t("panel.type") }}</div><div class="kv-v"><Icon :name="panel.vehicle.sheet === 'CAR' ? 'car' : 'bike'" :size="14" /> {{ panel.vehicle.sheet === "CAR" ? t("sheet.car") : t("sheet.bike") }}</div></div>
            <div class="kv"><div class="kv-l">{{ t("panel.model") }}</div><div class="kv-v">{{ panel.vehicle.vehicle_type || t("common.none") }}</div></div>
            <div class="kv"><div class="kv-l">{{ t("panel.fuel") }}</div><div class="kv-v">{{ panel.vehicle.fuel || t("common.none") }}</div></div>
            <div class="kv"><div class="kv-l">{{ t("panel.rentalOffice") }}</div><div class="kv-v">{{ panel.vehicle.rental_office || t("common.none") }}</div></div>
            <div class="kv"><div class="kv-l">{{ t("panel.area") }}</div><div class="kv-v">{{ panel.vehicle.area || t("common.none") }}</div></div>
            <div class="kv"><div class="kv-l">{{ t("panel.project") }}</div><div class="kv-v">{{ trim(panel.vehicle.project) || t("common.none") }}</div></div>
            <div class="kv"><div class="kv-l">{{ t("panel.vehicleStatus") }}</div><div class="kv-v">{{ sb(panel.vehicle).label }}</div></div>
          </div>
          <!-- Fuel plan: demoted from the card to the detail panel -->
          <div class="psect-title"><Icon name="fuel" :size="14" /> {{ t("panel.fuelPlan") }}</div>
          <div class="vc-fuel-row" style="border-radius:var(--r2);border:1px solid var(--b1)">
            <div>
              <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
                <span class="fuel-grade-badge">{{ fuelView(panel.vehicle).gradeLabel }} · {{ fuelView(panel.vehicle).sarPerL }} {{ t("common.sarPerL") }}</span>
              </div>
              <div style="display:flex;align-items:baseline;gap:4px">
                <span class="fuel-sar-val">{{ fuelView(panel.vehicle).sarDisplay }}</span>
                <span class="fuel-sar-unit">{{ t("common.sar") }}</span>
                <span class="fuel-sar-period">{{ t("common.perDay") }}</span>
                <span v-if="fuelView(panel.vehicle).dailySAR > 0" class="fuel-monthly" style="margin-inline-start:8px">· {{ fuelView(panel.vehicle).monDisplay }} {{ t("common.perMonthSuffix") }}</span>
              </div>
            </div>
          </div>
          <template v-if="panel.vehicle.current_driver">
            <div class="psect-title"><Icon name="user" :size="14" /> {{ t("panel.currentDriver") }}</div>
            <div class="cur-driver-card">
              <div class="cdc-av">{{ initials(panel.vehicle.current_driver) }}</div>
              <div class="cdc-info">
                <div class="cdc-name">{{ panel.vehicle.current_driver.name_ar || panel.vehicle.current_driver.name_en || t("common.none") }}</div>
                <div class="cdc-en">{{ panel.vehicle.current_driver.name_en || "" }}</div>
                <div class="cdc-chips">
                  <span class="cdc-chip"><Icon name="phone" :size="11" /> <bdi>{{ panel.vehicle.current_driver.mobile || t("common.none") }}</bdi></span>
                  <span class="cdc-chip"><Icon name="id-card" :size="11" /> <bdi>{{ panel.vehicle.current_driver.driver_id || t("common.none") }}</bdi></span>
                  <span class="cdc-chip"><Icon name="calendar" :size="11" /> <bdi>{{ panel.vehicle.current_driver.date_receive || t("common.none") }}</bdi></span>
                </div>
              </div>
              <span class="lock-pill"><Icon name="lock" :size="12" /> {{ t("panel.active") }}</span>
            </div>
          </template>
        </div>

        <!-- TAB 1: DRIVER -->
        <div v-else-if="panel.tab === 1" class="pb on">
          <template v-if="panel.vehicle.current_driver">
            <div class="alert alert-green"><Icon name="lock" :size="15" /> {{ t("driverTab.lockedFor", { name: panel.vehicle.current_driver.name_ar || panel.vehicle.current_driver.name_en }) }}</div>
            <div class="psect-title">{{ t("driverTab.currentDriverData") }}</div>
            <div class="kv-grid">
              <div class="kv"><div class="kv-l">{{ t("driverTab.nameAr") }}</div><div class="kv-v">{{ panel.vehicle.current_driver.name_ar || t("common.none") }}</div></div>
              <div class="kv"><div class="kv-l">{{ t("driverTab.nameEn") }}</div><div class="kv-v">{{ panel.vehicle.current_driver.name_en || t("common.none") }}</div></div>
              <div class="kv"><div class="kv-l">{{ t("driverTab.iqama") }}</div><div class="kv-v mono"><bdi>{{ panel.vehicle.current_driver.driver_id || t("common.none") }}</bdi></div></div>
              <div class="kv"><div class="kv-l">{{ t("driverTab.mobile") }}</div><div class="kv-v mono"><bdi>{{ panel.vehicle.current_driver.mobile || t("common.none") }}</bdi></div></div>
              <div class="kv"><div class="kv-l">{{ t("driverTab.project") }}</div><div class="kv-v">{{ trim(panel.vehicle.current_driver.project) || t("common.none") }}</div></div>
              <div class="kv"><div class="kv-l">{{ t("driverTab.area") }}</div><div class="kv-v">{{ panel.vehicle.current_driver.area || t("common.none") }}</div></div>
              <div class="kv"><div class="kv-l">{{ t("driverTab.receiveDate") }}</div><div class="kv-v mono"><bdi>{{ panel.vehicle.current_driver.date_receive || t("common.none") }}</bdi></div></div>
              <div class="kv"><div class="kv-l">{{ t("driverTab.receiveBranch") }}</div><div class="kv-v">{{ panel.vehicle.current_driver.branch_receive || t("common.none") }}</div></div>
            </div>
            <div class="psect-title">{{ t("driverTab.actions") }}</div>
            <div style="display:flex;gap:8px">
              <button class="btn btn-red" style="flex:1" @click="openStopForm"><Icon name="circle-pause" :size="15" /> {{ t("driverTab.stopAndLock") }}</button>
              <button class="btn btn-green" style="flex:1" @click="openReassignForm"><Icon name="rotate-cw" :size="15" /> {{ t("driverTab.reassignNew") }}</button>
            </div>
            <!-- Stop sub-form -->
            <div v-if="subForm === 'stop'" style="margin-top:14px;border:1px solid rgba(244,63,94,.2);border-radius:var(--r2);padding:14px;background:var(--red-d)">
              <div class="psect-title" style="color:var(--red-l)"><Icon name="circle-pause" :size="14" /> {{ t("stopForm.title") }}</div>
              <div class="form-grid" style="margin-bottom:10px">
                <div class="ff"><div class="fl">{{ t("stopForm.deliverDate") }} *</div><input class="fi" type="date" v-model="sf.date" /></div>
                <div class="ff"><div class="fl">{{ t("stopForm.deliverBranch") }}</div><input class="fi" v-model="sf.branch" :placeholder="t('stopForm.branchPlaceholder')" /></div>
                <div class="ff"><div class="fl">{{ t("stopForm.stopReason") }}</div>
                  <select class="fsel" v-model="sf.reason">
                    <option value="">{{ t("stopForm.chooseReason") }}</option>
                    <option :value="t('stopForm.reasonContractEnd')">{{ t("stopForm.reasonContractEnd") }}</option>
                    <option :value="t('stopForm.reasonTransfer')">{{ t("stopForm.reasonTransfer") }}</option>
                    <option :value="t('stopForm.reasonProjectStopped')">{{ t("stopForm.reasonProjectStopped") }}</option>
                    <option :value="t('stopForm.reasonVehicleFault')">{{ t("stopForm.reasonVehicleFault") }}</option>
                    <option :value="t('stopForm.reasonDriverRequest')">{{ t("stopForm.reasonDriverRequest") }}</option>
                    <option :value="t('stopForm.reasonViolation')">{{ t("stopForm.reasonViolation") }}</option>
                    <option :value="t('stopForm.reasonOther')">{{ t("stopForm.reasonOther") }}</option>
                  </select>
                </div>
                <div class="ff"><div class="fl">{{ t("stopForm.nextStatus") }}</div>
                  <select class="fsel" v-model="sf.nextStatus">
                    <option value="available">{{ t("stopForm.nextAvailable") }}</option>
                    <option value="workshop">{{ t("stopForm.nextWorkshop") }}</option>
                    <option value="stopped">{{ t("stopForm.nextStopped") }}</option>
                  </select>
                </div>
              </div>
              <div class="ff"><div class="fl">{{ t("stopForm.notes") }}</div><textarea class="fta" v-model="sf.notes" :placeholder="t('stopForm.notesPlaceholder')"></textarea></div>
              <div class="form-actions" style="margin-top:10px">
                <button class="btn" @click="closeSubForm()">{{ t("common.cancel") }}</button>
                <button class="btn btn-red" @click="confirmStop"><Icon name="circle-pause" :size="15" /> {{ t("stopForm.confirm") }}</button>
              </div>
            </div>
            <!-- Reassign sub-form -->
            <div v-if="subForm === 'reassign'" style="margin-top:14px;border:1px solid rgba(0,201,122,.2);border-radius:var(--r2);padding:14px;background:var(--green-d)">
              <div class="psect-title" style="color:var(--green-l)"><Icon name="rotate-cw" :size="14" /> {{ t("reassignForm.title") }}</div>
              <div class="alert alert-amber" style="margin-bottom:12px"><Icon name="triangle-alert" :size="15" /> {{ t("reassignForm.autoLockHint", { name: panel.vehicle.current_driver.name_ar || panel.vehicle.current_driver.name_en || t("common.none") }) }}</div>
              <div class="psect-title" style="color:var(--green-l);margin-top:12px">{{ t("reassignForm.newDriverData") }}</div>
              <div class="form-grid">
                <div class="ff" style="position:relative">
                  <div class="fl">{{ t("reassignForm.driver") }} *</div>
                  <input class="fi" v-model="dp.query" :placeholder="t('reassignForm.driverPlaceholder')" @input="onDriverQuery" @focus="dp.open = dp.results.length > 0" autocomplete="off" />
                  <div v-if="dp.loading" class="dp-hint">{{ t("reassignForm.searching") }}</div>
                  <div v-else-if="dp.open && !dp.results.length && trim(dp.query)" class="dp-hint">{{ t("reassignForm.noDrivers") }}</div>
                  <ul v-if="dp.open && dp.results.length" class="dp-menu">
                    <li v-for="d in dp.results" :key="d.name">
                      <button type="button" class="dp-opt" @click="pickDriver(d)">
                        <span class="dp-name">{{ d.full_name || d.name }}</span>
                        <span v-if="d.driver_id" class="dp-meta mono"><bdi>{{ d.driver_id }}</bdi></span>
                        <span v-if="d.phone" class="dp-meta mono"><bdi>{{ d.phone }}</bdi></span>
                      </button>
                    </li>
                  </ul>
                  <button type="button" class="dp-newlink" @click="openNewDriverForm"><Icon name="user" :size="13" /> {{ t("reassignForm.newDriver") }}</button>
                </div>
                <div class="ff"><div class="fl">{{ t("reassignForm.receiveDate") }}</div><input class="fi" type="date" v-model="rf.date" /></div>
              </div>
              <label class="ho-toggle"><input type="checkbox" v-model="rf.captureHandover" /> {{ t("reassignForm.captureHandover") }}</label>
              <div v-if="rf.captureHandover" class="ho-box">
                <div class="form-grid">
                  <div class="ff"><div class="fl">{{ t("reassignForm.odometer") }}</div><input class="fi mono" type="number" min="0" v-model="rf.odometer" /></div>
                  <div class="ff"><div class="fl">{{ t("reassignForm.checklistTemplate") }}</div><input class="fi" v-model="rf.checklistTemplate" :placeholder="t('reassignForm.checklistPlaceholder')" /></div>
                  <div class="ff" style="grid-column:1/-1"><div class="fl">{{ t("reassignForm.conditionNotes") }}</div><textarea class="fta" v-model="rf.conditionNotes"></textarea></div>
                </div>
                <div class="ho-hint"><Icon name="clipboard-list" :size="13" /> {{ t("reassignForm.handoverHint") }}</div>
              </div>
              <div class="form-actions" style="margin-top:12px">
                <button class="btn" @click="closeSubForm()">{{ t("common.cancel") }}</button>
                <button class="btn btn-green" :disabled="!rf.driverName" @click="submitReassign"><Icon name="lock" :size="15" /> {{ t("reassignForm.assignAndLock") }}</button>
              </div>
            </div>
          </template>
          <template v-else>
            <div v-if="panel.vehicle.vehicle_status === 'workshop'" class="alert alert-orange"><Icon name="wrench" :size="15" /> {{ t("driverTab.inWorkshopHint") }}</div>
            <div v-if="panel.vehicle.vehicle_status === 'stopped'" class="alert alert-amber"><Icon name="circle-pause" :size="15" /> {{ t("driverTab.stoppedHint") }}</div>
            <div class="psect-title">{{ t("driverTab.assignNewDriver") }}</div>
            <div class="form-grid">
              <div class="ff" style="position:relative">
                <div class="fl">{{ t("reassignForm.driver") }} *</div>
                <input class="fi" v-model="dp.query" :placeholder="t('reassignForm.driverPlaceholder')" @input="onDriverQuery" @focus="dp.open = dp.results.length > 0" autocomplete="off" />
                <div v-if="dp.loading" class="dp-hint">{{ t("reassignForm.searching") }}</div>
                <div v-else-if="dp.open && !dp.results.length && trim(dp.query)" class="dp-hint">{{ t("reassignForm.noDrivers") }}</div>
                <ul v-if="dp.open && dp.results.length" class="dp-menu">
                  <li v-for="d in dp.results" :key="d.name">
                    <button type="button" class="dp-opt" @click="pickDriver(d)">
                      <span class="dp-name">{{ d.full_name || d.name }}</span>
                      <span v-if="d.driver_id" class="dp-meta mono"><bdi>{{ d.driver_id }}</bdi></span>
                      <span v-if="d.phone" class="dp-meta mono"><bdi>{{ d.phone }}</bdi></span>
                    </button>
                  </li>
                </ul>
                <button type="button" class="dp-newlink" @click="openNewDriverForm"><Icon name="user" :size="13" /> {{ t("reassignForm.newDriver") }}</button>
              </div>
              <div class="ff"><div class="fl">{{ t("reassignForm.receiveDate") }}</div><input class="fi" type="date" v-model="rf.date" /></div>
            </div>
            <label class="ho-toggle"><input type="checkbox" v-model="rf.captureHandover" /> {{ t("reassignForm.captureHandover") }}</label>
            <div v-if="rf.captureHandover" class="ho-box">
              <div class="form-grid">
                <div class="ff"><div class="fl">{{ t("reassignForm.odometer") }}</div><input class="fi mono" type="number" min="0" v-model="rf.odometer" /></div>
                <div class="ff"><div class="fl">{{ t("reassignForm.checklistTemplate") }}</div><input class="fi" v-model="rf.checklistTemplate" :placeholder="t('reassignForm.checklistPlaceholder')" /></div>
                <div class="ff" style="grid-column:1/-1"><div class="fl">{{ t("reassignForm.conditionNotes") }}</div><textarea class="fta" v-model="rf.conditionNotes"></textarea></div>
              </div>
              <div class="ho-hint"><Icon name="clipboard-list" :size="13" /> {{ t("reassignForm.handoverHint") }}</div>
            </div>
            <div class="form-actions" style="margin-top:12px">
              <button class="btn btn-green" :disabled="!rf.driverName" @click="submitReassign"><Icon name="lock" :size="15" /> {{ t("reassignForm.assignAndLock") }}</button>
            </div>
          </template>
        </div>

        <!-- TAB 2: STATUS -->
        <div v-else-if="panel.tab === 2" class="pb on">
          <div class="psect-title">{{ t("statusTab.title") }}</div>
          <div class="status-grid">
            <button class="stpick" :class="panel.vehicle.vehicle_status === 'assigned' ? 'cur-assigned' : ''" @click="changeStatus(panel.vehicle.plate, 'assigned')">
              <span class="sp-ico"><Icon name="lock" :size="20" /></span><span class="sp-lbl" :style="{ color: panel.vehicle.vehicle_status === 'assigned' ? 'inherit' : 'var(--t2)' }">{{ t("statusTab.assignedLabel") }}</span><span class="sp-desc">{{ t("statusTab.assignedDesc") }}</span>
            </button>
            <button class="stpick" :class="panel.vehicle.vehicle_status === 'available' ? 'cur-available' : ''" @click="changeStatus(panel.vehicle.plate, 'available')">
              <span class="sp-ico"><Icon name="key" :size="20" /></span><span class="sp-lbl" :style="{ color: panel.vehicle.vehicle_status === 'available' ? 'inherit' : 'var(--t2)' }">{{ t("statusTab.availableLabel") }}</span><span class="sp-desc">{{ t("statusTab.availableDesc") }}</span>
            </button>
            <button class="stpick" :class="panel.vehicle.vehicle_status === 'workshop' ? 'cur-workshop' : ''" @click="changeStatus(panel.vehicle.plate, 'workshop')">
              <span class="sp-ico"><Icon name="wrench" :size="20" /></span><span class="sp-lbl" :style="{ color: panel.vehicle.vehicle_status === 'workshop' ? 'inherit' : 'var(--t2)' }">{{ t("statusTab.workshopLabel") }}</span><span class="sp-desc">{{ t("statusTab.workshopDesc") }}</span>
            </button>
            <button class="stpick" :class="panel.vehicle.vehicle_status === 'stopped' ? 'cur-stopped' : ''" @click="changeStatus(panel.vehicle.plate, 'stopped')">
              <span class="sp-ico"><Icon name="circle-pause" :size="20" /></span><span class="sp-lbl" :style="{ color: panel.vehicle.vehicle_status === 'stopped' ? 'inherit' : 'var(--t2)' }">{{ t("statusTab.stoppedLabel") }}</span><span class="sp-desc">{{ t("statusTab.stoppedDesc") }}</span>
            </button>
            <button class="stpick" :class="panel.vehicle.vehicle_status === 'stolen' ? 'cur-stopped' : ''" @click="changeStatus(panel.vehicle.plate, 'stolen')">
              <span class="sp-ico"><Icon name="shield-alert" :size="20" /></span><span class="sp-lbl" :style="{ color: panel.vehicle.vehicle_status === 'stolen' ? 'inherit' : 'var(--t2)' }">{{ t("statusTab.stolenLabel") }}</span><span class="sp-desc">{{ t("statusTab.stolenDesc") }}</span>
            </button>
          </div>
          <template v-if="panel.vehicle.vehicle_status === 'workshop'">
            <button class="btn btn-green" style="width:100%;justify-content:center" @click="changeStatus(panel.vehicle.plate, 'available')"><Icon name="circle-check" :size="15" /> {{ t("statusTab.exitWorkshop") }}</button>
          </template>
          <template v-if="panel.vehicle.vehicle_status === 'stolen'">
            <button class="btn btn-green" style="width:100%;justify-content:center;margin-top:8px" @click="recoverVehicle(panel.vehicle.plate)"><Icon name="lock-open" :size="15" /> {{ t("statusTab.recoverVehicle") }}</button>
          </template>
          <template v-if="panel.vehicle.vehicle_status === 'available' || panel.vehicle.vehicle_status === 'stopped'">
            <div class="psect-title" style="color:var(--red-l)"><Icon name="shield-alert" :size="14" /> {{ t("statusTab.reportTheft") }}</div>
            <button class="btn btn-red" style="width:100%;justify-content:center" @click="openStolenForm"><Icon name="shield-alert" :size="15" /> {{ t("statusTab.reportTheftBtn") }}</button>
            <div v-if="subForm === 'stolen'" style="border:1px solid rgba(124,58,237,.2);border-radius:var(--r2);padding:14px;background:var(--purple-d);margin-top:10px">
              <div class="psect-title" style="color:var(--purple-l)"><Icon name="shield-alert" :size="14" /> {{ t("stolenForm.title") }}</div>
              <div class="form-grid">
                <div class="ff"><div class="fl">{{ t("stolenForm.theftDate") }} *</div><input class="fi" type="date" v-model="stf.date" /></div>
                <div class="ff"><div class="fl">{{ t("stolenForm.policeNumber") }}</div><input class="fi mono" v-model="stf.police" :placeholder="t('stolenForm.policePlaceholder')" /></div>
                <div class="ff"><div class="fl">{{ t("stolenForm.location") }}</div><input class="fi" v-model="stf.location" :placeholder="t('stolenForm.locationPlaceholder')" /></div>
                <div class="ff"><div class="fl">{{ t("stolenForm.reportedBy") }}</div><input class="fi" v-model="stf.reporter" :placeholder="t('stolenForm.reporterPlaceholder')" /></div>
                <div class="ff" style="grid-column:1/-1"><div class="fl">{{ t("stolenForm.details") }}</div><textarea class="fta" v-model="stf.desc" :placeholder="t('stolenForm.detailsPlaceholder')"></textarea></div>
                <div class="ff" style="grid-column:1/-1"><div class="fl">{{ t("stolenForm.extraNotes") }}</div><textarea class="fta" v-model="stf.notes"></textarea></div>
              </div>
              <div class="form-actions" style="margin-top:10px">
                <button class="btn" @click="closeSubForm()">{{ t("common.cancel") }}</button>
                <button class="btn" style="background:var(--purple);color:#fff;border-color:var(--purple)" @click="submitStolen"><Icon name="shield-alert" :size="15" /> {{ t("stolenForm.confirm") }}</button>
              </div>
            </div>
          </template>
        </div>

        <!-- TAB 3: DAMAGES (live API has none → empty state) -->
        <div v-else-if="panel.tab === 3" class="pb on">
          <div class="psect-title"><Icon name="hammer" :size="14" /> {{ t("damages.title") }}</div>
          <div v-if="!(panel.vehicle.damages || []).length" class="empty"><div class="empty-ic"><Icon name="hammer" :size="42" :stroke-width="1.5" /></div><div>{{ t("damages.empty") }}</div></div>
          <div v-for="(d, i) in panel.vehicle.damages || []" :key="i" class="incident-card">
            <div class="incident-card-head">
              <div style="display:flex;align-items:center;gap:8px">
                <span class="incident-badge" :class="d.status === 'completed' ? 'incident-badge-ok' : ''"><Icon :name="d.status === 'completed' ? 'circle-check' : 'hammer'" :size="12" />{{ d.status === "completed" ? t("damages.repaired") : t("damages.damage") }}</span>
                <span style="font-size:12px;font-weight:600;color:var(--t1)"><bdi>{{ d.date || t("common.none") }}</bdi></span>
              </div>
              <div style="display:flex;gap:6px"><span v-if="d.cost" style="font-size:11px;color:var(--amber-l);font-weight:600;display:inline-flex;align-items:center;gap:3px"><Icon name="banknote" :size="12" /> {{ d.cost }} {{ t("common.sar") }}</span></div>
            </div>
            <div class="incident-card-body">
              <div class="inc-row"><span class="inc-label">{{ t("damages.description") }}</span>{{ d.description || t("common.none") }}</div>
            </div>
          </div>
        </div>

        <!-- TAB 4: ACCIDENTS (live API has none → empty state) -->
        <div v-else-if="panel.tab === 4" class="pb on">
          <div class="psect-title"><Icon name="crash" :size="14" /> {{ t("accidents.title") }}</div>
          <div v-if="!(panel.vehicle.accidents || []).length" class="empty"><div class="empty-ic"><Icon name="crash" :size="42" :stroke-width="1.5" /></div><div>{{ t("accidents.empty") }}</div></div>
          <div v-for="(a, i) in panel.vehicle.accidents || []" :key="i" class="incident-card">
            <div class="incident-card-head">
              <div style="display:flex;align-items:center;gap:8px">
                <span class="incident-badge incident-badge-acc" :class="a.status === 'closed' ? 'incident-badge-ok' : ''"><Icon :name="a.status === 'closed' ? 'circle-check' : 'crash'" :size="12" />{{ a.status === "closed" ? t("accidents.closed") : t("accidents.accident") }}</span>
                <span style="font-size:12px;font-weight:600;color:var(--t1)"><bdi>{{ a.date || t("common.none") }}</bdi></span>
              </div>
            </div>
            <div class="incident-card-body">
              <div class="inc-row"><span class="inc-label">{{ t("accidents.description") }}</span>{{ a.description || t("common.none") }}</div>
            </div>
          </div>
        </div>

        <!-- TAB 5: LOG -->
        <div v-else-if="panel.tab === 5" class="pb on">
          <div v-if="!panel.vehicle.history.length" class="empty"><div class="empty-ic"><Icon name="clipboard-list" :size="42" :stroke-width="1.5" /></div><div>{{ t("logTab.empty") }}</div></div>
          <template v-else>
            <div class="psect-title">{{ t("logTab.fullTimeline", { n: panel.vehicle.history.length }) }}</div>
            <div class="tl">
              <div v-for="(item, i) in historyItems(panel.vehicle)" :key="i" class="tl-item">
                <div class="tl-ic" :class="item.d.status === 'Active' ? 'ti-active' : 'ti-stopped'"><Icon name="user" :size="15" /></div>
                <div class="tl-info">
                  <div class="tl-head">
                    {{ item.d.name_ar || item.d.name_en || t("logTab.driver") }}
                    <span class="tl-status" :class="item.d.status === 'Active' ? 'tls-active' : 'tls-stopped'"><Icon :name="item.d.status === 'Active' ? 'circle-check' : 'circle-pause'" :size="11" />{{ item.d.status === "Active" ? t("logTab.active") : t("logTab.ended") }}</span>
                  </div>
                  <div class="tl-sub">{{ item.d.name_en || "" }} · <Icon name="phone" :size="11" /> <bdi>{{ item.d.mobile || t("common.none") }}</bdi> · <Icon name="id-card" :size="11" /> <bdi>{{ item.d.driver_id || t("common.none") }}</bdi></div>
                  <div class="tl-sub"><Icon name="package" :size="11" /> {{ trim(item.d.project) || t("common.none") }} · <Icon name="pin" :size="11" /> {{ item.d.area || t("common.none") }} · <Icon name="building" :size="11" /> {{ item.d.branch_receive || t("common.none") }}</div>
                  <span class="tl-dates"><bdi>{{ item.d.date_receive || t("common.none") }}</bdi> → <bdi>{{ item.d.date_deliver || (item.d.status === "Active" ? t("common.ongoing") : t("common.none")) }}</bdi></span>
                  <span v-if="calcDur(item.d.date_receive, item.d.date_deliver || (item.d.status === 'Active' ? today() : ''))" class="tl-dur">{{ calcDur(item.d.date_receive, item.d.date_deliver || (item.d.status === "Active" ? today() : "")) }}</span>
                  <div v-if="item.d.reason" class="tl-reason">{{ t("logTab.reason", { v: item.d.reason }) }}</div>
                  <div v-if="item.d.notes" class="tl-note">{{ t("logTab.note", { v: item.d.notes }) }}</div>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </transition>
</template>
