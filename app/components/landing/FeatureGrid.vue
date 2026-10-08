<script setup lang="ts">
// One numbered section of the landing page: a heading, a lead, and a cell per feature.
export interface Feature {
  title: string
  text: string
}

defineProps<{ id: string, number?: number, title: string, lead?: string, features: Feature[], columns?: 2 | 3 }>()
</script>

<template>
  <section
    :aria-labelledby="id"
    class="flex flex-col gap-5"
  >
    <SectionHeading
      :id="id"
      :number="number"
      :title="title"
    />
    <p
      v-if="lead"
      class="max-w-2xl text-[15px] text-muted text-pretty"
    >
      {{ lead }}
    </p>
    <ul
      class="grid gap-3"
      :class="columns === 2 ? 'sm:grid-cols-2' : 'sm:grid-cols-2 lg:grid-cols-3'"
    >
      <li
        v-for="feature in features"
        :key="feature.title"
        class="surface flex flex-col gap-2 p-5 sm:p-6"
      >
        <h3 class="text-base font-semibold text-highlighted">
          {{ feature.title }}
        </h3>
        <p class="text-sm text-muted text-pretty">
          {{ feature.text }}
        </p>
      </li>
    </ul>
  </section>
</template>
