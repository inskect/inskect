<script setup lang="ts">
// A password field with a show/hide toggle. Every other attribute (id, autocomplete, size…) goes
// to the underlying UInput.
defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<{
  // What the toggle names in its label, e.g. "Show API key".
  subject?: string
}>(), { subject: 'password' })

const model = defineModel<string>({ default: '' })
const visible = ref(false)
const attrs = useAttrs()
</script>

<template>
  <UInput
    v-bind="attrs"
    v-model="model"
    :type="visible ? 'text' : 'password'"
    :ui="{ trailing: 'pe-1' }"
  >
    <template #trailing>
      <UButton
        color="neutral"
        variant="link"
        size="sm"
        :icon="visible ? 'i-lucide-eye-off' : 'i-lucide-eye'"
        :aria-label="`${visible ? 'Hide' : 'Show'} ${props.subject}`"
        :aria-pressed="visible"
        :aria-controls="typeof attrs.id === 'string' ? attrs.id : undefined"
        class="text-dimmed hover:text-highlighted"
        @click="visible = !visible"
      />
    </template>
  </UInput>
</template>
