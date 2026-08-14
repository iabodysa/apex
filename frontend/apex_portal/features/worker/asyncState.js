import { computed, nextTick, reactive, ref, watch } from "vue";

export function createDraftAction(initial, { store = null, key = "" } = {}) {
  const defaults = { ...initial };
  const restored = store && key ? store.read(key) : null;
  const draft = reactive({ ...defaults, ...(restored || {}) });
  const state = ref("ready");
  const error = ref("");
  let persistenceEnabled = true;
  const dirty = computed(() => Object.keys(defaults)
    .some((field) => draft[field] !== defaults[field]));

  if (store && key) {
    watch(draft, (value) => {
      if (persistenceEnabled) store.write(key, { ...value });
    }, { deep: true });
  }

  async function resetDraft() {
    persistenceEnabled = false;
    for (const field of Object.keys(draft)) {
      if (!(field in defaults)) delete draft[field];
    }
    Object.assign(draft, defaults);
    await nextTick();
    if (store && key) store.clear(key);
    persistenceEnabled = true;
  }

  async function submit(operation) {
    state.value = "saving";
    error.value = "";
    try {
      const result = await operation({ ...draft });
      await resetDraft();
      state.value = "saved";
      return result;
    } catch (reason) {
      state.value = "error";
      error.value = reason?.message || "تعذّر الحفظ. حاول مرة أخرى.";
      return undefined;
    }
  }

  async function discard() {
    error.value = "";
    state.value = "ready";
    await resetDraft();
  }

  return { draft, state, error, dirty, submit, discard };
}
