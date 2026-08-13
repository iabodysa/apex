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
const requests = createListResource({ doctype: "Maintenance Request", auto: false });
const rooms = createListResource({
  doctype: "Room",
  fields: ["name", "room_number"],
  orderBy: "room_number asc",
  pageLength: 500,
  auto: false,
});
const roomOptions = computed(() =>
  (rooms.data || []).map((row) => ({
    label: row.room_number || row.name,
    value: row.name,
  })),
);
watch(
  building,
  async (value) => {
    form.room = "";
    if (value) {
      rooms.update({ filters: { building: value } });
      await rooms.reload();
    }
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
      <Button type="submit" theme="green" variant="solid" :loading="requests.insert.loading" :disabled="!building || !form.room || !form.issue_description">إرسال الطلب</Button>
    </form>
  </section>
</template>
