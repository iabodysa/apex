<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { Badge, Button, FormControl, createResource } from "frappe-ui";
import AsyncPanel from "../components/AsyncPanel.vue";
import { createSingleFlight } from "../state.js";
import { statusLabel, statusTheme } from "../../../core/displayLabels.js";
const route = useRoute(),
  complaint = createResource({
    url: "apex.salis.api.fleet_employee.get_complaint",
    method: "GET",
    auto: false,
  }),
  replyResource = createResource({
    url: "apex.salis.api.fleet_employee.reply_to_complaint",
    method: "POST",
    auto: false,
  }),
  message = ref(""),
  notice = ref(""),
  issue = computed(() => complaint.data || null),
  once = createSingleFlight();
const load = () => complaint.fetch({ name: route.params.name });
async function reply() {
  await once(`reply:${route.params.name}`, () => replyResource.submit({ name: route.params.name, message: message.value }));
  message.value = "";
  notice.value = "تم إرسال الرد";
  await load();
}
onMounted(load);
</script>
<template>
  <section class="salis-page">
    <AsyncPanel v-if="complaint.loading" state="loading" title="جاري تحميل البلاغ" message="نسترجع المحادثة." />
    <AsyncPanel v-else-if="complaint.error" state="error" title="تعذر فتح البلاغ" message="قد لا يكون ضمن سجلاتك." @retry="load" />
    <article v-else-if="issue" class="salis-card">
      <Badge :theme="statusTheme(issue.status)" :label="statusLabel(issue.status)" />
      <h2>{{ issue.subject }}</h2>
      <p>{{ issue.description }}</p>
      <ul class="salis-list">
        <li v-for="item in issue.communications || []" :key="item.name">
          <div>
            <strong>{{ item.sender }}</strong>
            <p>{{ item.content }}</p>
          </div>
        </li>
      </ul>
      <form class="salis-form" @submit.prevent="reply">
        <FormControl v-model="message" type="textarea" :rows="3" label="ردك" required />
        <p v-if="notice" class="salis-notice">{{ notice }}</p>
        <Button type="submit" variant="solid" theme="green" label="إرسال الرد" :loading="replyResource.loading" />
      </form>
    </article>
  </section>
</template>
