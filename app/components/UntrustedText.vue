<script setup lang="ts">
// A name from a scanned skill (its name, a file path, the target), shown so it can't read as
// something else (shared/utils/textSafety.ts): invisible and reordering characters appear as their
// code points, letters from another alphabet are marked, and a warning icon says what's there.
const props = defineProps<{ value: string | null | undefined }>()

const parts = computed(() => inspectText(props.value ?? ''))
const summary = computed(() => parts.value.some(part => part.kind) ? suspiciousSummary(props.value ?? '') : '')
</script>

<template>
  <bdi class="untrusted-text">
    <template
      v-for="(part, index) in parts"
      :key="index"
    >
      <template v-if="!part.kind">{{ part.text }}</template>
      <mark
        v-else-if="part.kind === 'mixed-script'"
        class="bg-medium-tint px-px text-medium-ink underline decoration-wavy"
        :title="`${part.codePoint}, from another alphabet than the rest of the word`"
      >{{ part.text }}</mark>
      <span
        v-else
        class="mx-px bg-medium-tint px-1 font-mono text-[0.75em] text-medium-ink"
        :title="part.kind === 'bidi' ? 'A character that reorders the text around it' : 'An invisible character'"
      >{{ part.codePoint }}</span>
    </template>
    <span
      v-if="summary"
      role="img"
      :aria-label="`Deceptive characters: ${summary}`"
      :title="`Deceptive characters: ${summary}`"
      class="ml-1 inline-flex align-[-0.15em]"
    >
      <UIcon
        name="i-lucide-triangle-alert"
        class="size-3.5 text-medium-ink"
      />
    </span>
  </bdi>
</template>

<style scoped>
.untrusted-text {
  unicode-bidi: isolate;
}
</style>
