<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { Badge, Button, FormControl } from "frappe-ui";
import AsyncPanel from "../components/AsyncPanel.vue";
import { createFleetSelfResources } from "../api.js";
import { createSingleFlight } from "../state.js";
const route = useRoute(),
    r = createFleetSelfResources(),
    message = ref(""),
    notice = ref(""),
    issue = computed(() => r.complaint.data || null),
    once = createSingleFlight();
const load = () => r.complaint.fetch({ name: route.params.name });
async function reply() {
    await once(`reply:${route.params.name}`, () =>
        r.replyComplaint.submit({ name: route.params.name, message: message.value }),
    );
    message.value = "";
    notice.value = "تم إرسال الرد";
    await load();
}
onMounted(load);
</script>
<template>
    <section class="salis-page">
        <AsyncPanel
            v-if="r.complaint.loading"
            state="loading"
            title="جاري تحميل البلاغ"
            message="نسترجع المحادثة."
        /><AsyncPanel
            v-else-if="r.complaint.error"
            state="error"
            title="تعذر فتح البلاغ"
            message="قد لا يكون ضمن سجلاتك."
            @retry="load"
        />
        <article v-else-if="issue" class="salis-card">
            <Badge theme="green" :label="issue.status" />
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
                <Button
                    type="submit"
                    variant="solid"
                    theme="green"
                    label="إرسال الرد"
                    :loading="r.replyComplaint.loading"
                />
            </form>
        </article>
    </section>
</template>
