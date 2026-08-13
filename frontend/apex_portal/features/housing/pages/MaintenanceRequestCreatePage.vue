<script setup>
import { computed, reactive, ref, watch } from "vue";
import { Button, ErrorMessage, FormControl, createListResource, toast } from "frappe-ui";
import BuildingPicker from "../components/BuildingPicker.vue";
import { building } from "../building.js";

const form = reactive({
  room: "",
  issue_type: "Other",
  issue_description: "",
  priority: "Medium",
});
const error = ref("");
const roomError = ref("");
const loadedBuilding = ref("");
const requests = createListResource({ doctype: "Maintenance Request", auto: false });
const rooms = createListResource({
  doctype: "Room",
  fields: ["name", "room_number"],
  orderBy: "room_number asc, name asc",
  pageLength: 100,
  auto: false,
});
const roomOptions = computed(() =>
  loadedBuilding.value === building.value
    ? (rooms.data || []).map((row) => ({ label: row.room_number || row.name, value: row.name }))
    : [],
);
let roomLoadQueue = Promise.resolve();

async function loadAllRooms(value) {
  rooms.update({ filters: { building: value }, start: 0 });
  await rooms.reload();
  while (rooms.hasNextPage) {
    rooms.update({ start: rooms.start + rooms.pageLength });
    await rooms.list.fetch();
  }
}

watch(
  building,
  (value) => {
    form.room = "";
    loadedBuilding.value = "";
    roomError.value = "";
    if (!value) return;
    roomLoadQueue = roomLoadQueue.then(async () => {
      if (building.value !== value) return;
      try {
        await loadAllRooms(value);
        if (building.value === value) loadedBuilding.value = value;
      } catch (exception) {
        if (building.value === value) {
          roomError.value = exception?.message || "تعذّر تحميل غرف المبنى.";
        }
      }
    });
  },
  { immediate: true },
);
async function submit() {
  error.value = "";
  try {
    const result = await requests.insert.submit({ building: building.value, ...form });
    toast.create({
      type: "success",
      message: result?.name ? `تم تسجيل طلب الصيانة ${result.name}` : "تم تسجيل طلب الصيانة",
    });
    Object.assign(form, {
      room: "",
      issue_type: "Other",
      issue_description: "",
      priority: "Medium",
    });
  } catch (exception) {
    error.value = exception.message || "تعذر تسجيل الطلب.";
  }
}
</script>
<template>
  <section class="feature-page">
    <h2>طلب صيانة جديد</h2>
    <BuildingPicker />
    <form class="feature-form" @submit.prevent="submit">
      <ErrorMessage v-if="roomError" :message="roomError" />
      <FormControl v-model="form.room" type="select" label="الغرفة" :options="roomOptions" required />
      <FormControl
        v-model="form.issue_type"
        type="select"
        label="نوع المشكلة"
        :options="[
          { label: 'كهرباء', value: 'Electrical' },
          { label: 'سباكة', value: 'Plumbing' },
          { label: 'أثاث', value: 'Furniture' },
          { label: 'تكييف', value: 'Air Conditioning' },
          { label: 'سلامة الحريق', value: 'Fire Safety' },
          { label: 'مكافحة آفات', value: 'Pest Control' },
          { label: 'إنشائي', value: 'Structural' },
          { label: 'أخرى', value: 'Other' },
        ]"
        required
      />
      <FormControl v-model="form.issue_description" type="textarea" label="وصف المشكلة" required />
      <FormControl
        v-model="form.priority"
        type="select"
        label="الأولوية"
        :options="[
          { label: 'منخفضة', value: 'Low' },
          { label: 'متوسطة', value: 'Medium' },
          { label: 'عالية', value: 'High' },
          { label: 'حرجة', value: 'Critical' },
        ]"
      />
      <ErrorMessage v-if="error" :message="error" />
      <Button type="submit" theme="green" variant="solid" :loading="requests.insert.loading" :disabled="rooms.list.loading || !building || !form.room || !form.issue_description">إرسال الطلب</Button>
    </form>
  </section>
</template>
