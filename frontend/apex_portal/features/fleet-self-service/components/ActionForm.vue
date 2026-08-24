<script setup>
import { reactive, ref } from "vue";
import { Button, FileUploader, FormControl } from "frappe-ui";
import { createSingleFlight } from "../state.js";
import { statusLabel } from "../../../core/displayLabels.js";
import { safeErrorMessage } from "../../../core/errorMessage.js";
import { __ } from "../../../core/i18n.js";

const props = defineProps({
    title: { type: String, required: true },
    intro: String,
    fields: Array,
    resource: { type: Object, required: true },
    actionKey: String,
});
const emit = defineEmits(["saved"]);
const form = reactive(
    Object.fromEntries((props.fields || []).map((field) => [field.name, field.default ?? ""])),
);
const notice = ref("");
const error = ref("");
const submitOnce = createSingleFlight();

function onUploaded(field, result) {
    form[field] = result?.file_url || "";
}
async function submit() {
    notice.value = "";
    error.value = "";
    try {
        const result = await submitOnce(props.actionKey, () => props.resource.submit({ ...form }));
        notice.value = __("Saved with status: {0}", [statusLabel(result?.status || "Pending")]);
        emit("saved", result);
    } catch (caught) {
        error.value = safeErrorMessage(caught, __("Could not save. Your data stayed as you entered it."));
    }
}
</script>

<template>
    <section class="salis-page salis-form-page">
        <header>
            <p class="salis-eyebrow">{{ __("Salis") }}</p>
            <h2>{{ title }}</h2>
            <p>{{ intro }}</p>
        </header>
        <form class="salis-form" @submit.prevent="submit">
            <template v-for="field in fields" :key="field.name">
                <FileUploader
                    v-if="field.type === 'file'"
                    :file-types="['image/*', 'application/pdf']"
                    :upload-args="{ private: 1, folder: 'Home/Attachments' }"
                    @success="onUploaded(field.name, $event)"
                >
                    <template #default="{ openFileSelector, uploading, error: uploadError }">
                        <div class="salis-upload">
                            <span>{{ field.label }}</span
                            ><Button
                                type="button"
                                variant="outline"
                                :loading="uploading"
                                :label="form[field.name] ? __('File Attached') : __('Attach File')"
                                @click="openFileSelector"
                            />
                            <p v-if="uploadError">{{ __("Could not upload the file.") }}</p>
                        </div>
                    </template>
                </FileUploader>
                <FormControl
                    v-else
                    v-model="form[field.name]"
                    :type="field.type || 'text'"
                    size="lg"
                    :label="field.label"
                    :options="field.options"
                    :rows="field.rows"
                    :required="field.required"
                    :disabled="field.disabled"
                    :description="field.description"
                />
            </template>
            <p v-if="notice" class="salis-notice" role="status">{{ notice }}</p>
            <p v-if="error" class="salis-error" role="alert">{{ error }}</p>
            <Button
                type="submit"
                variant="solid"
                theme="green"
                size="lg"
                :label="__('Send')"
                :loading="resource.loading"
            />
        </form>
    </section>
</template>
