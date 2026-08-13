import { reactive, ref, watch } from "vue";

export function createDraftAction(initial, { store = null, key = "" } = {}) {
  const restored = store && key ? store.read(key) : null;
  const draft = reactive({ ...initial, ...(restored || {}) });
  const state = ref("ready");
  const error = ref("");

  if (store && key) {
    watch(draft, (value) => store.write(key, { ...value }), { deep: true });
  }

  async function submit(operation) {
    state.value = "saving";
    error.value = "";
    try {
      const result = await operation({ ...draft });
      state.value = "saved";
      if (store && key) store.clear(key);
      return result;
    } catch (reason) {
      state.value = "error";
      error.value = reason?.message || "تعذّر الحفظ. حاول مرة أخرى.";
      return undefined;
    }
  }

  return { draft, state, error, submit };
}
